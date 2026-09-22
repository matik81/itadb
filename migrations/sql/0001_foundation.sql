CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA catalog;
CREATE SCHEMA geo;
CREATE SCHEMA stats;
CREATE SCHEMA api;

CREATE TABLE catalog.source (
    id text PRIMARY KEY,
    name text NOT NULL,
    homepage text NOT NULL,
    license_url text NOT NULL,
    is_demo boolean NOT NULL DEFAULT false
);
CREATE TABLE catalog.dataset (
    id text PRIMARY KEY,
    source_id text NOT NULL REFERENCES catalog.source(id),
    title text NOT NULL,
    description text NOT NULL,
    limitations text NOT NULL
);
CREATE TABLE catalog.release (
    id uuid PRIMARY KEY,
    dataset_id text NOT NULL REFERENCES catalog.dataset(id),
    reference_period date NOT NULL,
    retrieved_at timestamptz NOT NULL,
    published_at timestamptz,
    upstream_url text NOT NULL,
    raw_sha256 text NOT NULL CHECK (raw_sha256 ~ '^[a-f0-9]{64}$'),
    transform_version text NOT NULL,
    contract_sha256 text NOT NULL CHECK (contract_sha256 ~ '^[a-f0-9]{64}$'),
    license_url text NOT NULL,
    status text NOT NULL CHECK (status IN ('draft','validated','published')),
    row_count bigint NOT NULL CHECK (row_count >= 0),
    UNIQUE (dataset_id, raw_sha256, transform_version, contract_sha256),
    CHECK ((status = 'published') = (published_at IS NOT NULL))
);
CREATE INDEX release_published ON catalog.release (dataset_id, published_at DESC)
    WHERE status = 'published';
CREATE TABLE catalog.artifact (
    release_id uuid NOT NULL REFERENCES catalog.release(id),
    kind text NOT NULL CHECK (kind IN ('raw','curated','quality')),
    uri text NOT NULL,
    sha256 text NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    PRIMARY KEY (release_id, kind)
);
CREATE TABLE catalog.pipeline_run (
    id uuid PRIMARY KEY,
    release_id uuid REFERENCES catalog.release(id),
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('running','failed','succeeded')),
    error_code text,
    CHECK ((status = 'running') = (finished_at IS NULL))
);
CREATE TABLE catalog.quality_result (
    release_id uuid NOT NULL REFERENCES catalog.release(id),
    check_name text NOT NULL,
    passed boolean NOT NULL,
    details jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (release_id, check_name)
);

-- A code alone is not an identity: boundaries and municipal codes change over time.
CREATE TABLE geo.territory (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scheme text NOT NULL,
    code text NOT NULL,
    name text NOT NULL,
    level text NOT NULL CHECK (level IN ('country','region','province','municipality')),
    valid_from date NOT NULL,
    valid_to date,
    parent_id bigint REFERENCES geo.territory(id),
    UNIQUE (scheme, code, valid_from),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
CREATE INDEX territory_parent ON geo.territory(parent_id);
CREATE TABLE geo.boundary (
    territory_id bigint NOT NULL REFERENCES geo.territory(id),
    release_id uuid NOT NULL REFERENCES catalog.release(id),
    geom geometry(MultiPolygon, 4326) NOT NULL,
    PRIMARY KEY (territory_id, release_id),
    CHECK (ST_IsValid(geom))
);
CREATE INDEX boundary_gist ON geo.boundary USING gist (geom);
CREATE TABLE stats.series (
    id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE,
    title text NOT NULL,
    unit text NOT NULL,
    dimensions jsonb NOT NULL DEFAULT '{}',
    CHECK (jsonb_typeof(dimensions) = 'object')
);
-- Release is mandatory in API queries, enabling partition pruning. Eight bounded
-- hash partitions avoid one partition per release and unbounded planning overhead.
CREATE TABLE stats.observation (
    release_id uuid NOT NULL REFERENCES catalog.release(id),
    series_id smallint NOT NULL REFERENCES stats.series(id),
    territory_id bigint NOT NULL REFERENCES geo.territory(id),
    period date NOT NULL,
    value numeric(20,6),
    status text NOT NULL CHECK (status IN ('observed','estimated','missing','suppressed','demo')),
    PRIMARY KEY (release_id, series_id, period, territory_id),
    CHECK ((status IN ('missing','suppressed')) = (value IS NULL)),
    CHECK (value IS NULL OR value::text NOT IN ('NaN','Infinity','-Infinity'))
) PARTITION BY HASH (release_id);
DO $$
BEGIN
    FOR i IN 0..7 LOOP
        EXECUTE format('CREATE TABLE stats.observation_p%s PARTITION OF stats.observation FOR VALUES WITH (MODULUS 8, REMAINDER %s)', i, i);
    END LOOP;
END $$;

CREATE FUNCTION catalog.protect_published_release() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status = 'published' THEN
        RAISE EXCEPTION 'Published evidence is immutable; create a new release';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER release_immutable BEFORE UPDATE OR DELETE ON catalog.release
FOR EACH ROW EXECUTE FUNCTION catalog.protect_published_release();

CREATE FUNCTION catalog.protect_published_child() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE rid uuid;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        rid := OLD.release_id;
        PERFORM 1 FROM catalog.release WHERE id = rid AND status = 'published' FOR SHARE;
        IF FOUND THEN RAISE EXCEPTION 'Published evidence is immutable'; END IF;
    END IF;
    IF TG_OP <> 'DELETE' THEN
        rid := NEW.release_id;
        -- Serialize mutations with publication, including concurrent writers.
        PERFORM 1 FROM catalog.release WHERE id = rid FOR SHARE;
        IF EXISTS (SELECT 1 FROM catalog.release WHERE id = rid AND status = 'published')
        THEN RAISE EXCEPTION 'Published evidence is immutable'; END IF;
        RETURN NEW;
    END IF;
    RETURN OLD;
END $$;
CREATE TRIGGER observation_immutable BEFORE INSERT OR UPDATE OR DELETE ON stats.observation
FOR EACH ROW EXECUTE FUNCTION catalog.protect_published_child();
CREATE TRIGGER artifact_immutable BEFORE INSERT OR UPDATE OR DELETE ON catalog.artifact
FOR EACH ROW EXECUTE FUNCTION catalog.protect_published_child();
CREATE TRIGGER quality_immutable BEFORE INSERT OR UPDATE OR DELETE ON catalog.quality_result
FOR EACH ROW EXECUTE FUNCTION catalog.protect_published_child();
CREATE TRIGGER boundary_immutable BEFORE INSERT OR UPDATE OR DELETE ON geo.boundary
FOR EACH ROW EXECUTE FUNCTION catalog.protect_published_child();

-- Referenced dimension values must not silently change historical evidence.
CREATE FUNCTION catalog.protect_dimension() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE used boolean;
BEGIN
    IF TG_TABLE_NAME = 'territory' THEN
        SELECT EXISTS (SELECT 1 FROM stats.observation o JOIN catalog.release r
            ON r.id=o.release_id WHERE o.territory_id=OLD.id AND r.status='published') INTO used;
    ELSIF TG_TABLE_NAME = 'series' THEN
        SELECT EXISTS (SELECT 1 FROM stats.observation o JOIN catalog.release r
            ON r.id=o.release_id WHERE o.series_id=OLD.id AND r.status='published') INTO used;
    ELSIF TG_TABLE_NAME = 'dataset' THEN
        SELECT EXISTS (SELECT 1 FROM catalog.release WHERE dataset_id=OLD.id AND status='published') INTO used;
    ELSE
        SELECT EXISTS (SELECT 1 FROM catalog.dataset d JOIN catalog.release r ON r.dataset_id=d.id
            WHERE d.source_id=OLD.id AND r.status='published') INTO used;
    END IF;
    IF used THEN RAISE EXCEPTION 'Published dimensions are immutable; create a new version'; END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER territory_immutable BEFORE UPDATE OR DELETE ON geo.territory
FOR EACH ROW EXECUTE FUNCTION catalog.protect_dimension();
CREATE TRIGGER series_immutable BEFORE UPDATE OR DELETE ON stats.series
FOR EACH ROW EXECUTE FUNCTION catalog.protect_dimension();
CREATE TRIGGER dataset_immutable BEFORE UPDATE OR DELETE ON catalog.dataset
FOR EACH ROW EXECUTE FUNCTION catalog.protect_dimension();
CREATE TRIGGER source_immutable BEFORE UPDATE OR DELETE ON catalog.source
FOR EACH ROW EXECUTE FUNCTION catalog.protect_dimension();

CREATE VIEW api.sources AS SELECT id, name, homepage, license_url, is_demo FROM catalog.source;
CREATE VIEW api.releases AS
SELECT r.id, r.dataset_id, d.title, d.limitations, d.source_id, s.is_demo,
       r.reference_period, r.retrieved_at, r.published_at, r.upstream_url,
       r.raw_sha256, r.transform_version, r.contract_sha256, r.license_url, r.row_count
FROM catalog.release r JOIN catalog.dataset d ON d.id=r.dataset_id
JOIN catalog.source s ON s.id=d.source_id WHERE r.status='published';
CREATE VIEW api.observations AS
SELECT o.release_id, s.code AS series_code, s.unit, t.id AS territory_id,
       t.code AS territory_code, t.name AS territory_name, t.scheme,
       o.period, o.value, o.status
FROM stats.observation o JOIN catalog.release r ON r.id=o.release_id AND r.status='published'
JOIN stats.series s ON s.id=o.series_id JOIN geo.territory t ON t.id=o.territory_id;
CREATE VIEW api.quality AS
SELECT q.release_id, q.check_name, q.passed, q.details FROM catalog.quality_result q
JOIN catalog.release r ON r.id=q.release_id WHERE r.status='published';

INSERT INTO catalog.source VALUES
('demo','Itadb — fixture dimostrativa','https://github.com/matik81/itadb','https://creativecommons.org/publicdomain/zero/1.0/',true),
('istat','ISTAT','https://www.istat.it','https://www.istat.it/note-legali/',false),
('eurostat','Eurostat','https://ec.europa.eu/eurostat','https://ec.europa.eu/eurostat/about-us/policies/copyright',false);
INSERT INTO catalog.dataset VALUES
('demo_population','demo','Popolazione — dimostrazione tecnica',
 'Valori inventati per verificare la pipeline; non sono statistiche italiane.',
 'Tre territori fittizi, nessuna copertura nazionale e nessun valore inferenziale.');
INSERT INTO stats.series(code,title,unit,dimensions)
VALUES ('population_total','Popolazione totale','persons','{"age":"TOTAL","sex":"TOTAL"}');
