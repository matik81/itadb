-- Synthetic records have their own schema and never enter observed statistics.
CREATE SCHEMA population;
CREATE TABLE population.snapshot (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id text NOT NULL UNIQUE CHECK (run_id ~ '^[0-9a-f]{64}$'),
    manifest_sha256 text NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    status text NOT NULL DEFAULT 'loading' CHECK (status IN ('loading','published')),
    reference_date date NOT NULL,
    household_reference date NOT NULL,
    persons bigint NOT NULL CHECK (persons > 0),
    households bigint NOT NULL CHECK (households > 0),
    municipalities integer NOT NULL CHECK (municipalities > 0),
    is_fixture boolean NOT NULL DEFAULT false,
    report jsonb NOT NULL,
    provenance jsonb NOT NULL,
    publication_checks jsonb NOT NULL DEFAULT '{}',
    published_at timestamptz,
    CHECK ((status='published') = (published_at IS NOT NULL))
);
CREATE TABLE population.municipality (
    snapshot_id bigint NOT NULL REFERENCES population.snapshot(id),
    code integer NOT NULL CHECK(code BETWEEN 1 AND 999999),
    name text NOT NULL,
    province_code smallint NOT NULL,
    province_name text NOT NULL,
    region_code smallint NOT NULL,
    region_name text NOT NULL,
    persons bigint NOT NULL,
    households bigint NOT NULL,
    boundary geometry(MultiPolygon,4326),
    center geometry(Point,4326),
    PRIMARY KEY(snapshot_id,code)
);
CREATE INDEX population_municipality_region ON population.municipality(snapshot_id,region_code,code);
CREATE TABLE population.region (
    snapshot_id bigint NOT NULL REFERENCES population.snapshot(id),
    code smallint NOT NULL,
    name text NOT NULL,
    boundary geometry(MultiPolygon,4326),
    PRIMARY KEY(snapshot_id,code)
);
CREATE TABLE population.household (
    snapshot_id bigint NOT NULL,
    household_id bigint NOT NULL CHECK(household_id>0),
    municipality_code integer NOT NULL,
    size smallint NOT NULL CHECK(size BETWEEN 1 AND 6),
    PRIMARY KEY(snapshot_id,household_id)
) PARTITION BY LIST(snapshot_id);
CREATE INDEX population_household_municipality ON population.household(snapshot_id,municipality_code,household_id);
CREATE TABLE population.person (
    snapshot_id bigint NOT NULL,
    person_id bigint NOT NULL CHECK(person_id>0),
    household_id bigint CHECK(household_id>0),
    municipality_code integer NOT NULL,
    sex text NOT NULL CHECK(sex IN ('M','F')),
    birth_year smallint,
    birth_year_upper_bound smallint,
    citizenship_code smallint NOT NULL CHECK(citizenship_code BETWEEN 1 AND 999),
    reference_adult boolean NOT NULL,
    PRIMARY KEY(snapshot_id,person_id),
    CHECK((birth_year IS NULL) <> (birth_year_upper_bound IS NULL)),
    CHECK(NOT reference_adult OR household_id IS NOT NULL)
) PARTITION BY LIST(snapshot_id);
CREATE INDEX population_person_municipality ON population.person(snapshot_id,municipality_code,person_id);
CREATE INDEX population_person_household ON population.person(snapshot_id,household_id,person_id) WHERE household_id IS NOT NULL;
-- Small typed cube, derived from the imported persons, for interactive distributions.
CREATE TABLE population.cell (
    snapshot_id bigint NOT NULL,
    municipality_code integer NOT NULL,
    sex text NOT NULL CHECK(sex IN ('M','F')),
    age smallint NOT NULL CHECK(age BETWEEN 0 AND 100),
    citizenship_code smallint NOT NULL,
    persons bigint NOT NULL CHECK(persons>0),
    PRIMARY KEY(snapshot_id,municipality_code,sex,age,citizenship_code)
) PARTITION BY LIST(snapshot_id);
CREATE TABLE population.validation (
    snapshot_id bigint NOT NULL,
    municipality_code integer NOT NULL,
    kind text NOT NULL CHECK(kind IN ('sex_age','foreign_age','citizenship','household_size')),
    sex text NOT NULL,
    category smallint NOT NULL,
    expected bigint NOT NULL CHECK(expected>=0),
    actual bigint NOT NULL CHECK(actual>=0),
    PRIMARY KEY(snapshot_id,municipality_code,kind,sex,category)
) PARTITION BY LIST(snapshot_id);
-- Statement triggers on each record partition avoid a trigger call per individual.
CREATE FUNCTION population.guard_partition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM population.snapshot WHERE id=TG_ARGV[0]::bigint AND status='published') THEN
        RAISE EXCEPTION 'Published population is immutable';
    END IF;
    RETURN NULL;
END $$;
CREATE FUNCTION population.guard_parent() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Write only through the snapshot importer partitions';
END $$;
CREATE TRIGGER population_person_guard BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON population.person
FOR EACH STATEMENT EXECUTE FUNCTION population.guard_parent();
CREATE TRIGGER population_household_guard BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON population.household
FOR EACH STATEMENT EXECUTE FUNCTION population.guard_parent();
CREATE FUNCTION population.guard_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP<>'INSERT' AND EXISTS(SELECT 1 FROM population.snapshot WHERE id=OLD.snapshot_id AND status='published') THEN
        RAISE EXCEPTION 'Published population evidence is immutable';
    END IF;
    IF TG_OP<>'DELETE' AND EXISTS(SELECT 1 FROM population.snapshot WHERE id=NEW.snapshot_id AND status='published') THEN
        RAISE EXCEPTION 'Published population evidence is immutable';
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;
CREATE TRIGGER region_guard BEFORE INSERT OR UPDATE OR DELETE ON population.region
FOR EACH ROW EXECUTE FUNCTION population.guard_evidence();
CREATE TRIGGER municipality_guard BEFORE INSERT OR UPDATE OR DELETE ON population.municipality
FOR EACH ROW EXECUTE FUNCTION population.guard_evidence();
CREATE TRIGGER cell_guard BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON population.cell
FOR EACH STATEMENT EXECUTE FUNCTION population.guard_parent();
CREATE TRIGGER validation_guard BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON population.validation
FOR EACH STATEMENT EXECUTE FUNCTION population.guard_parent();
CREATE FUNCTION population.guard_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
    IF TG_OP<>'INSERT' AND OLD.status='published' THEN
        RAISE EXCEPTION 'Published population snapshot is immutable';
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    IF NEW.status='published' THEN
        SELECT count(*) INTO n FROM population.person WHERE snapshot_id=NEW.id;
        IF n<>NEW.persons THEN RAISE EXCEPTION 'Population person count differs'; END IF;
        SELECT count(*) INTO n FROM population.household WHERE snapshot_id=NEW.id;
        IF n<>NEW.households THEN RAISE EXCEPTION 'Population household count differs'; END IF;
        SELECT count(*) INTO n FROM population.municipality WHERE snapshot_id=NEW.id;
        IF n<>NEW.municipalities THEN RAISE EXCEPTION 'Population geography count differs'; END IF;
        IF NOT (NEW.publication_checks @> '{"snapshot_audit": true,"database_constraints": true,"database_relationships": true}'::jsonb)
           OR NOT EXISTS (SELECT 1 FROM population.validation WHERE snapshot_id=NEW.id)
           OR EXISTS (SELECT 1 FROM population.validation WHERE snapshot_id=NEW.id AND actual<>expected)
           OR (SELECT coalesce(sum(persons),0) FROM population.cell WHERE snapshot_id=NEW.id)<>NEW.persons THEN
            RAISE EXCEPTION 'Population publication checks failed';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER snapshot_guard BEFORE INSERT OR UPDATE OR DELETE ON population.snapshot
FOR EACH ROW EXECUTE FUNCTION population.guard_snapshot();
CREATE VIEW api.population_snapshots AS SELECT id,run_id,manifest_sha256,reference_date,household_reference,
    persons,households,municipalities,is_fixture,published_at,'synthetic'::text AS data_kind,
    0::bigint AS located_persons,report,provenance,publication_checks
FROM population.snapshot WHERE status='published';
CREATE VIEW api.population_municipalities AS SELECT m.* FROM population.municipality m
JOIN population.snapshot s ON s.id=m.snapshot_id AND s.status='published';
CREATE VIEW api.population_persons AS SELECT p.*,s.reference_date,
    extract(year FROM s.reference_date)::int-1-coalesce(p.birth_year,p.birth_year_upper_bound) AS age,
    p.birth_year IS NULL AS age_is_lower_bound,'synthetic'::text AS data_kind
FROM population.person p JOIN population.snapshot s ON s.id=p.snapshot_id AND s.status='published';
CREATE VIEW api.population_households AS SELECT h.*,'synthetic'::text AS data_kind FROM population.household h
JOIN population.snapshot s ON s.id=h.snapshot_id AND s.status='published';
CREATE VIEW api.population_cells AS SELECT c.*,m.region_code,m.province_code FROM population.cell c
JOIN population.municipality m ON m.snapshot_id=c.snapshot_id AND m.code=c.municipality_code
JOIN population.snapshot s ON s.id=c.snapshot_id AND s.status='published';
CREATE VIEW api.population_validation AS SELECT v.* FROM population.validation v
JOIN population.snapshot s ON s.id=v.snapshot_id AND s.status='published';
REVOKE ALL ON SCHEMA population FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA population FROM PUBLIC;

CREATE VIEW api.population_regions AS SELECT r.* FROM population.region r
JOIN population.snapshot s ON s.id=r.snapshot_id AND s.status='published';
