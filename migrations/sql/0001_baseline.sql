-- Initial consolidated schema. Historical revisions 0001–0006 are preserved in Git
-- at commit 9cd934a; new installations start directly at 0001_baseline.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;
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
CREATE TABLE stats.series (
    id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE,
    title text NOT NULL,
    unit text NOT NULL,
    dimensions jsonb NOT NULL DEFAULT '{}',
    CHECK (jsonb_typeof(dimensions) = 'object')
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
    CONSTRAINT release_content_identity UNIQUE
        (dataset_id,raw_sha256,transform_version,contract_sha256,metadata_sha256),
    CHECK ((status = 'published') = (published_at IS NOT NULL)),
    api_version smallint NOT NULL DEFAULT 1 CHECK (api_version IN (1,2)),
    metadata_sha256 text NOT NULL DEFAULT repeat('0',64)
        CHECK (metadata_sha256 ~ '^[a-f0-9]{64}$'),
    upstream_last_update timestamptz,
    upstream_published_at timestamptz,
    supersedes_release_id uuid,
    revision_reason text,
    territory_snapshot date,
    series_code text NOT NULL DEFAULT 'population_total' REFERENCES stats.series(code),
    attribution text,
    CONSTRAINT release_revision_identity UNIQUE (id,dataset_id,reference_period),
    CONSTRAINT release_predecessor FOREIGN KEY
        (supersedes_release_id,dataset_id,reference_period)
        REFERENCES catalog.release(id,dataset_id,reference_period),
    CONSTRAINT release_revision_reason CHECK (
        (supersedes_release_id IS NULL AND revision_reason IS NULL) OR
        (supersedes_release_id IS NOT NULL AND revision_reason IS NOT NULL
         AND length(trim(revision_reason)) BETWEEN 1 AND 1000 AND supersedes_release_id <> id)
    ),
    publication_kind text NOT NULL DEFAULT 'legacy' CHECK (publication_kind IN ('legacy','coverage'))
);
CREATE INDEX release_published ON catalog.release (dataset_id, published_at DESC)
    WHERE status = 'published';
CREATE TABLE catalog.artifact (
    release_id uuid NOT NULL REFERENCES catalog.release(id),
    kind text NOT NULL CHECK (kind IN
        ('raw','curated','quality','structure','dataflow','contract','onboarding_contract',
         'data_manifest','structure_manifest','dataflow_manifest','license','onboarding',
         'evidence','geography','crosswalk')),
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
    CONSTRAINT territory_no_overlap EXCLUDE USING gist (scheme WITH =, code WITH =,
        daterange(valid_from,valid_to,'[)') WITH &&),
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
-- Release is mandatory in API queries, enabling partition pruning. Eight bounded
-- hash partitions avoid one partition per release and unbounded planning overhead.
CREATE TABLE stats.observation (
    release_id uuid NOT NULL REFERENCES catalog.release(id),
    series_id smallint NOT NULL REFERENCES stats.series(id),
    territory_id bigint NOT NULL REFERENCES geo.territory(id),
    period date NOT NULL,
    value numeric(20,6),
    status text NOT NULL CHECK (status IN ('observed','estimated','missing','suppressed','demo','unflagged_upstream')),
    PRIMARY KEY (release_id, series_id, period, territory_id),
    CHECK ((status IN ('missing','suppressed')) = (value IS NULL)),
    CHECK (value IS NULL OR value::text NOT IN ('NaN','Infinity','-Infinity')),
    upstream_status text NOT NULL DEFAULT '',
    upstream_note text NOT NULL DEFAULT '',
    upstream_unit text NOT NULL DEFAULT '',
    upstream_unit_multiplier text NOT NULL DEFAULT ''
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
JOIN catalog.source s ON s.id=d.source_id WHERE r.status='published' AND r.api_version=1;
CREATE VIEW api.observations AS
SELECT o.release_id, s.code AS series_code, s.unit, t.id AS territory_id,
       t.code AS territory_code, t.name AS territory_name, t.scheme,
       o.period, o.value, o.status
FROM stats.observation o JOIN catalog.release r
    ON r.id=o.release_id AND r.status='published' AND r.api_version=1
JOIN stats.series s ON s.id=o.series_id JOIN geo.territory t ON t.id=o.territory_id;
CREATE VIEW api.quality AS
SELECT q.release_id, q.check_name, q.passed, q.details FROM catalog.quality_result q
JOIN catalog.release r ON r.id=q.release_id WHERE r.status='published' AND r.api_version=1;

INSERT INTO catalog.source VALUES
('demo','Itadb — fixture dimostrativa','urn:itadb:demo','https://creativecommons.org/publicdomain/zero/1.0/',true),
('istat','ISTAT','https://www.istat.it','https://www.istat.it/note-legali/',false),
('eurostat','Eurostat','https://ec.europa.eu/eurostat','https://ec.europa.eu/eurostat/about-us/policies/copyright',false);
INSERT INTO catalog.dataset VALUES
('demo_population','demo','Popolazione — dimostrazione tecnica',
 'Valori inventati per verificare la pipeline; non sono statistiche italiane.',
 'Tre territori fittizi, nessuna copertura nazionale e nessun valore inferenziale.');
INSERT INTO stats.series(code,title,unit,dimensions)
VALUES ('population_total','Popolazione totale','persons','{"age":"TOTAL","sex":"TOTAL"}');

CREATE UNIQUE INDEX release_one_successor ON catalog.release(supersedes_release_id)
    WHERE supersedes_release_id IS NOT NULL;
CREATE UNIQUE INDEX release_one_v2_root ON catalog.release(dataset_id,reference_period)
    WHERE api_version=2 AND supersedes_release_id IS NULL;

CREATE FUNCTION geo.check_territory_hierarchy() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent geo.territory;
BEGIN
    IF NEW.parent_id IS NOT NULL THEN
        SELECT * INTO STRICT parent FROM geo.territory WHERE id=NEW.parent_id FOR SHARE;
        IF parent.scheme <> NEW.scheme OR parent.id=NEW.id
           OR array_position(ARRAY['country','region','province','municipality'],parent.level)
              >= array_position(ARRAY['country','region','province','municipality'],NEW.level)
           OR NOT (daterange(parent.valid_from,parent.valid_to,'[)') @>
                   daterange(NEW.valid_from,NEW.valid_to,'[)')) THEN
            RAISE EXCEPTION 'Inconsistent territorial hierarchy';
        END IF;
    END IF;
    IF TG_OP='UPDATE' AND EXISTS (
        SELECT 1 FROM geo.territory child WHERE child.parent_id=OLD.id AND
        (child.scheme <> NEW.scheme OR
         array_position(ARRAY['country','region','province','municipality'],NEW.level)
           >= array_position(ARRAY['country','region','province','municipality'],child.level) OR
         NOT (daterange(NEW.valid_from,NEW.valid_to,'[)') @>
              daterange(child.valid_from,child.valid_to,'[)')))
    ) THEN RAISE EXCEPTION 'Territorial update invalidates children'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER territory_hierarchy BEFORE INSERT OR UPDATE ON geo.territory
FOR EACH ROW EXECUTE FUNCTION geo.check_territory_hierarchy();

CREATE FUNCTION stats.check_observation_context() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE territory geo.territory; release catalog.release; demo boolean;
BEGIN
    SELECT * INTO STRICT territory FROM geo.territory WHERE id=NEW.territory_id FOR SHARE;
    IF NOT (daterange(territory.valid_from,territory.valid_to,'[)') @> NEW.period) THEN
        RAISE EXCEPTION 'Observation falls outside territorial validity';
    END IF;
    SELECT * INTO STRICT release FROM catalog.release WHERE id=NEW.release_id FOR SHARE;
    SELECT s.is_demo INTO STRICT demo FROM catalog.dataset d
        JOIN catalog.source s ON s.id=d.source_id WHERE d.id=release.dataset_id;
    IF (NOT demo AND NEW.status='demo') OR
       (release.api_version=1 AND NEW.status='unflagged_upstream') OR
       (release.api_version=2 AND release.publication_kind='legacy' AND
        (NEW.period<>release.reference_period OR NOT EXISTS
         (SELECT 1 FROM stats.series WHERE id=NEW.series_id AND code=release.series_code))) OR
       (release.publication_kind='coverage' AND NOT EXISTS (
        SELECT 1 FROM catalog.coverage c JOIN geo.release_territory rt
        ON rt.release_id=c.release_id AND rt.territory_id=NEW.territory_id
        AND rt.snapshot=c.territory_snapshot
        WHERE c.release_id=NEW.release_id AND c.series_id=NEW.series_id
        AND c.period=NEW.period AND c.scheme=territory.scheme))
    THEN RAISE EXCEPTION 'Observation is incompatible with its release'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER observation_context BEFORE INSERT OR UPDATE ON stats.observation
FOR EACH ROW EXECUTE FUNCTION stats.check_observation_context();

CREATE FUNCTION catalog.check_legacy_release_publication() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.supersedes_release_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM catalog.release WHERE id=NEW.supersedes_release_id
        AND dataset_id=NEW.dataset_id AND reference_period=NEW.reference_period
        AND status='published' AND api_version=NEW.api_version FOR SHARE
    ) THEN RAISE EXCEPTION 'Revision requires a published compatible predecessor'; END IF;
    IF NEW.api_version=2 AND NEW.status='published' THEN
        IF NEW.row_count=0 OR NEW.row_count<>(
            SELECT count(*) FROM stats.observation WHERE release_id=NEW.id
        ) OR NOT EXISTS (SELECT 1 FROM catalog.quality_result WHERE release_id=NEW.id)
          OR EXISTS (SELECT 1 FROM catalog.quality_result WHERE release_id=NEW.id AND NOT passed)
        THEN RAISE EXCEPTION 'Publication quality gate failed'; END IF;
        IF (SELECT count(*) FROM catalog.artifact WHERE release_id=NEW.id AND kind IN
            ('raw','curated','quality','structure','dataflow','contract','onboarding_contract',
             'data_manifest','structure_manifest','dataflow_manifest','license','onboarding')) <> 12
        THEN RAISE EXCEPTION 'Publication provenance is incomplete'; END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER release_publication BEFORE INSERT OR UPDATE ON catalog.release
FOR EACH ROW WHEN (NEW.publication_kind='legacy')
EXECUTE FUNCTION catalog.check_legacy_release_publication();

-- Original v1 columns and enum remain unchanged. Official releases use v2.

CREATE VIEW api.releases_v2 AS
SELECT r.id, r.dataset_id, d.title, d.limitations, d.source_id, s.is_demo,
       r.reference_period, r.retrieved_at, r.published_at, r.upstream_url,
       r.raw_sha256, r.transform_version, r.contract_sha256, r.license_url, r.row_count,
       r.metadata_sha256, r.upstream_last_update, r.upstream_published_at,
       r.supersedes_release_id, r.revision_reason, r.territory_snapshot, r.series_code,
       r.attribution
FROM catalog.release r JOIN catalog.dataset d ON d.id=r.dataset_id
JOIN catalog.source s ON s.id=d.source_id WHERE r.status='published';
CREATE VIEW api.observations_v2 AS
SELECT o.release_id, s.code AS series_code, s.unit, t.id AS territory_id,
       t.code AS territory_code, t.name AS territory_name, t.scheme,
       o.period, o.value, o.status, t.level, parent.code AS parent_code,
       o.upstream_status, o.upstream_note, o.upstream_unit, o.upstream_unit_multiplier
FROM stats.observation o JOIN catalog.release r ON r.id=o.release_id AND r.status='published'
JOIN stats.series s ON s.id=o.series_id JOIN geo.territory t ON t.id=o.territory_id
LEFT JOIN geo.territory parent ON parent.id=t.parent_id;
CREATE VIEW api.quality_v2 AS
SELECT q.release_id,q.check_name,q.passed,q.details FROM catalog.quality_result q
JOIN catalog.release r ON r.id=q.release_id WHERE r.status='published';
CREATE VIEW api.artifacts_v2 AS
SELECT a.release_id,a.kind,a.sha256,a.byte_size FROM catalog.artifact a
JOIN catalog.release r ON r.id=a.release_id WHERE r.status='published';

INSERT INTO catalog.dataset(id,source_id,title,description,limitations) VALUES
('istat_population_regions','istat','Popolazione residente — regioni, 1° gennaio 2024',
 'IstatData: totale per sesso, età e stato civile; 20 regioni e Italia come controllo.',
 'Un solo istante, senza confini geografici. Italia è il totale di controllo: non sommarlo alle regioni. '
 'Senza flag upstream non significa osservazione diretta. Data di pubblicazione upstream non accertata.');
INSERT INTO stats.series(code,title,unit,dimensions) VALUES
('resident_population_jan1','Popolazione residente al 1° gennaio','persons',
 '{"frequency":"A","data_type":"JAN","sex":"9","age":"TOTAL","marital_status":"99","source":"istat"}');

CREATE TABLE catalog.coverage (
    release_id uuid NOT NULL REFERENCES catalog.release(id),
    series_id smallint NOT NULL REFERENCES stats.series(id),
    period date NOT NULL,
    scheme text NOT NULL,
    territory_snapshot date NOT NULL,
    row_count bigint NOT NULL CHECK (row_count > 0),
    PRIMARY KEY (release_id,series_id,period)
);
CREATE TRIGGER coverage_immutable BEFORE INSERT OR UPDATE OR DELETE ON catalog.coverage
FOR EACH ROW EXECUTE FUNCTION catalog.protect_published_child();

CREATE TABLE geo.release_territory (
    release_id uuid NOT NULL REFERENCES catalog.release(id),
    territory_id bigint NOT NULL REFERENCES geo.territory(id),
    snapshot date NOT NULL,
    PRIMARY KEY (release_id,territory_id)
);
CREATE INDEX release_territory_snapshot ON geo.release_territory(release_id,snapshot,territory_id);
CREATE TRIGGER release_territory_immutable BEFORE INSERT OR UPDATE OR DELETE ON geo.release_territory
FOR EACH ROW EXECUTE FUNCTION catalog.protect_published_child();

CREATE TABLE geo.change_event (
    release_id uuid NOT NULL REFERENCES catalog.release(id),
    event_id text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('merger','split','recode','transfer')),
    effective_date date NOT NULL,
    source_url text NOT NULL,
    evidence_sha256 text NOT NULL CHECK (evidence_sha256 ~ '^[a-f0-9]{64}$'),
    description text NOT NULL CHECK (length(trim(description)) > 0),
    PRIMARY KEY (release_id,event_id)
);
CREATE TRIGGER change_event_immutable BEFORE INSERT OR UPDATE OR DELETE ON geo.change_event
FOR EACH ROW EXECUTE FUNCTION catalog.protect_published_child();

CREATE TABLE geo.crosswalk (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    release_id uuid NOT NULL,
    event_id text NOT NULL,
    from_territory_id bigint NOT NULL,
    to_territory_id bigint NOT NULL,
    allocation_weight numeric(20,12),
    weight_basis text NOT NULL CHECK (weight_basis IN ('exact','structural')),
    FOREIGN KEY (release_id,event_id) REFERENCES geo.change_event(release_id,event_id),
    FOREIGN KEY (release_id,from_territory_id) REFERENCES geo.release_territory,
    FOREIGN KEY (release_id,to_territory_id) REFERENCES geo.release_territory,
    UNIQUE (release_id,event_id,from_territory_id,to_territory_id),
    CHECK (from_territory_id <> to_territory_id),
    CHECK ((weight_basis='structural' AND allocation_weight IS NULL)
        OR (weight_basis='exact' AND allocation_weight=1))
);
CREATE INDEX crosswalk_page ON geo.crosswalk(release_id,id);
CREATE TRIGGER crosswalk_immutable BEFORE INSERT OR UPDATE OR DELETE ON geo.crosswalk
FOR EACH ROW EXECUTE FUNCTION catalog.protect_published_child();

CREATE FUNCTION geo.check_crosswalk() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE before_date date; after_date date; event geo.change_event; old_level text; new_level text;
BEGIN
    SELECT snapshot,t.level INTO STRICT before_date,old_level FROM geo.release_territory rt
        JOIN geo.territory t ON t.id=rt.territory_id
        WHERE rt.release_id=NEW.release_id AND territory_id=NEW.from_territory_id;
    SELECT snapshot,t.level INTO STRICT after_date,new_level FROM geo.release_territory rt
        JOIN geo.territory t ON t.id=rt.territory_id
        WHERE rt.release_id=NEW.release_id AND territory_id=NEW.to_territory_id;
    SELECT * INTO STRICT event FROM geo.change_event
        WHERE release_id=NEW.release_id AND event_id=NEW.event_id;
    IF NOT (before_date < event.effective_date AND event.effective_date <= after_date)
       OR old_level<>new_level OR (event.kind='split' AND NEW.weight_basis<>'structural')
    THEN RAISE EXCEPTION 'Invalid crosswalk context'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER crosswalk_context BEFORE INSERT OR UPDATE ON geo.crosswalk
FOR EACH ROW EXECUTE FUNCTION geo.check_crosswalk();

-- Protect geography referenced without observations, too (historical versions).
CREATE FUNCTION geo.protect_referenced_territory() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM geo.release_territory rt JOIN catalog.release r ON r.id=rt.release_id
        WHERE rt.territory_id=OLD.id AND r.status='published')
       OR EXISTS (SELECT 1 FROM geo.boundary b JOIN catalog.release r ON r.id=b.release_id
        WHERE b.territory_id=OLD.id AND r.status='published')
    THEN RAISE EXCEPTION 'Published geography is immutable'; END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER territory_geography_immutable BEFORE UPDATE OR DELETE ON geo.territory
FOR EACH ROW EXECUTE FUNCTION geo.protect_referenced_territory();

CREATE FUNCTION catalog.check_coverage_publication() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.api_version<>2 THEN RAISE EXCEPTION 'Coverage requires API v2'; END IF;
    IF NEW.supersedes_release_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM catalog.release WHERE id=NEW.supersedes_release_id
        AND dataset_id=NEW.dataset_id AND reference_period=NEW.reference_period
        AND status='published' AND publication_kind='coverage' FOR SHARE
    ) THEN RAISE EXCEPTION 'Revision requires compatible published predecessor'; END IF;
    IF NEW.status<>'published' THEN RETURN NEW; END IF;
    IF NEW.row_count=0 OR NEW.row_count<>(SELECT count(*) FROM stats.observation WHERE release_id=NEW.id)
       OR NEW.row_count<>(SELECT coalesce(sum(row_count),0) FROM catalog.coverage WHERE release_id=NEW.id)
       OR NOT EXISTS (SELECT 1 FROM catalog.coverage c JOIN stats.series s ON s.id=c.series_id
          WHERE c.release_id=NEW.id AND s.code=NEW.series_code AND c.period=NEW.reference_period)
       OR EXISTS (SELECT 1 FROM catalog.coverage c WHERE release_id=NEW.id AND c.row_count<>
          (SELECT count(*) FROM stats.observation o WHERE o.release_id=c.release_id
           AND o.series_id=c.series_id AND o.period=c.period))
       OR NOT EXISTS (SELECT 1 FROM catalog.quality_result WHERE release_id=NEW.id)
       OR EXISTS (SELECT 1 FROM catalog.quality_result WHERE release_id=NEW.id AND NOT passed)
    THEN RAISE EXCEPTION 'Coverage publication quality gate failed'; END IF;
    IF (SELECT count(*) FROM catalog.artifact WHERE release_id=NEW.id
        AND kind IN ('raw','curated','quality','contract','evidence','geography','crosswalk','license'))<>8
    THEN RAISE EXCEPTION 'Coverage provenance is incomplete'; END IF;
    IF EXISTS (SELECT 1 FROM geo.release_territory rt JOIN geo.territory t ON t.id=rt.territory_id
       WHERE rt.release_id=NEW.id AND t.level<>'country' AND NOT EXISTS
       (SELECT 1 FROM geo.boundary b WHERE b.release_id=rt.release_id AND b.territory_id=t.id))
    THEN RAISE EXCEPTION 'Missing boundary'; END IF;
    IF EXISTS (SELECT 1 FROM geo.change_event e WHERE e.release_id=NEW.id AND (
        (e.kind='merger' AND ((SELECT count(DISTINCT from_territory_id) FROM geo.crosswalk
             WHERE release_id=e.release_id AND event_id=e.event_id)<2 OR
             (SELECT count(DISTINCT to_territory_id) FROM geo.crosswalk
             WHERE release_id=e.release_id AND event_id=e.event_id)<>1)) OR
        (e.kind='split' AND ((SELECT count(DISTINCT from_territory_id) FROM geo.crosswalk
             WHERE release_id=e.release_id AND event_id=e.event_id)<>1 OR
             (SELECT count(DISTINCT to_territory_id) FROM geo.crosswalk
             WHERE release_id=e.release_id AND event_id=e.event_id)<2)) OR
        NOT EXISTS (SELECT 1 FROM geo.crosswalk WHERE release_id=e.release_id AND event_id=e.event_id)))
    THEN RAISE EXCEPTION 'Incomplete territorial event'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER coverage_publication BEFORE INSERT OR UPDATE ON catalog.release
FOR EACH ROW WHEN (NEW.publication_kind='coverage')
EXECUTE FUNCTION catalog.check_coverage_publication();

CREATE VIEW api.coverage_v2 AS
SELECT c.release_id,s.code AS series_code,s.title,s.unit,s.dimensions,c.period,
       c.scheme,c.territory_snapshot,c.row_count
FROM catalog.coverage c JOIN catalog.release r ON r.id=c.release_id AND r.status='published'
JOIN stats.series s ON s.id=c.series_id
UNION ALL
SELECT r.id,s.code,s.title,s.unit,s.dimensions,r.reference_period,NULL::text,
       r.territory_snapshot,r.row_count
FROM catalog.release r JOIN stats.series s ON s.code=r.series_code
WHERE r.status='published' AND r.publication_kind='legacy';

CREATE VIEW api.territories_v2 AS
SELECT rt.release_id,t.id AS territory_id,t.scheme,t.code,t.name,t.level,t.valid_from,t.valid_to,
       parent.code AS parent_code,rt.snapshot,
       b.territory_id IS NOT NULL AS has_boundary
FROM geo.release_territory rt JOIN catalog.release r ON r.id=rt.release_id AND r.status='published'
JOIN geo.territory t ON t.id=rt.territory_id LEFT JOIN geo.territory parent ON parent.id=t.parent_id
LEFT JOIN geo.boundary b ON b.release_id=rt.release_id AND b.territory_id=t.id;

CREATE VIEW api.boundaries_v2 AS
SELECT b.release_id,b.territory_id,b.geom FROM geo.boundary b
JOIN catalog.release r ON r.id=b.release_id WHERE r.status='published';

CREATE VIEW api.crosswalks_v2 AS
SELECT c.id,c.release_id,c.event_id,e.kind,e.effective_date,e.source_url,e.evidence_sha256,
       e.description,f.code AS from_code,f.scheme AS from_scheme,
       t.code AS to_code,t.scheme AS to_scheme,c.allocation_weight,c.weight_basis
FROM geo.crosswalk c JOIN geo.change_event e USING (release_id,event_id)
JOIN catalog.release r ON r.id=c.release_id AND r.status='published'
JOIN geo.territory f ON f.id=c.from_territory_id JOIN geo.territory t ON t.id=c.to_territory_id;

INSERT INTO catalog.dataset VALUES
('istat_m2','istat','Territori e demografia — M2',
 'Popolazione per sesso ed età, famiglie, abitazioni e geografie ISTAT versionate.',
 'Periodi e vintage distinti; selezionare una sola serie e un solo livello per aggregare. '
 'I crosswalk strutturali non sono pesi demografici. La copertura è dichiarata per ogni selezione; '
 'gli snapshot non costituiscono una ricostruzione continua di tutta la storia amministrativa.');

-- Draft metadata can change after row-level validation: recheck at publication.
CREATE FUNCTION catalog.recheck_coverage_context() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status<>'published' THEN RETURN NEW; END IF;
    IF EXISTS (
        SELECT 1 FROM stats.observation o JOIN geo.territory t ON t.id=o.territory_id
        LEFT JOIN catalog.coverage c ON c.release_id=o.release_id
          AND c.series_id=o.series_id AND c.period=o.period
        LEFT JOIN geo.release_territory rt ON rt.release_id=o.release_id
          AND rt.territory_id=o.territory_id
        WHERE o.release_id=NEW.id AND (c.release_id IS NULL OR rt.release_id IS NULL
          OR c.scheme<>t.scheme OR rt.snapshot<>c.territory_snapshot
          OR NOT (daterange(t.valid_from,t.valid_to,'[)') @> o.period))
    ) THEN RAISE EXCEPTION 'Coverage context changed before publication'; END IF;
    IF EXISTS (
        SELECT 1 FROM geo.release_territory rt JOIN geo.territory t ON t.id=rt.territory_id
        LEFT JOIN geo.release_territory parent ON parent.release_id=rt.release_id
          AND parent.territory_id=t.parent_id
        WHERE rt.release_id=NEW.id AND (
          NOT (daterange(t.valid_from,t.valid_to,'[)') @> rt.snapshot)
          OR (t.level<>'country' AND (parent.territory_id IS NULL OR parent.snapshot<>rt.snapshot)))
    ) THEN RAISE EXCEPTION 'Incomplete geographic hierarchy'; END IF;
    IF EXISTS (
        SELECT 1 FROM geo.boundary b LEFT JOIN geo.release_territory rt
          ON rt.release_id=b.release_id AND rt.territory_id=b.territory_id
        WHERE b.release_id=NEW.id AND (rt.territory_id IS NULL OR ST_IsEmpty(b.geom)
          OR NOT ST_CoveredBy(b.geom,ST_MakeEnvelope(6,35,19,48,4326)))
    ) THEN RAISE EXCEPTION 'Invalid boundary context'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER coverage_context_publication BEFORE INSERT OR UPDATE ON catalog.release
FOR EACH ROW WHEN (NEW.publication_kind='coverage')
EXECUTE FUNCTION catalog.recheck_coverage_context();

-- Recheck current draft evidence, not just the state seen when rows were inserted.
CREATE FUNCTION catalog.recheck_geographic_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE boundary_mode text;
BEGIN
    IF NEW.status<>'published' THEN RETURN NEW; END IF;
    IF EXISTS (
        SELECT 1 FROM geo.crosswalk c
        JOIN geo.change_event e USING (release_id,event_id)
        JOIN geo.release_territory f ON f.release_id=c.release_id
          AND f.territory_id=c.from_territory_id
        JOIN geo.release_territory t ON t.release_id=c.release_id
          AND t.territory_id=c.to_territory_id
        JOIN geo.territory ft ON ft.id=f.territory_id
        JOIN geo.territory tt ON tt.id=t.territory_id
        WHERE c.release_id=NEW.id AND (
          NOT (f.snapshot<e.effective_date AND e.effective_date<=t.snapshot)
          OR ft.level<>tt.level
          OR (e.kind IN ('split','transfer') AND c.weight_basis<>'structural'))
    ) THEN RAISE EXCEPTION 'Crosswalk context changed before publication'; END IF;
    -- Merger/split cardinalities remain enforced by coverage_publication.
    IF EXISTS (
        SELECT 1 FROM geo.change_event e JOIN geo.crosswalk c USING (release_id,event_id)
        WHERE e.release_id=NEW.id AND e.kind IN ('recode','transfer')
        GROUP BY e.event_id
        HAVING count(DISTINCT c.from_territory_id)<>1 OR count(DISTINCT c.to_territory_id)<>1
    ) THEN RAISE EXCEPTION 'Invalid recode or transfer cardinality'; END IF;
    SELECT details->>'parent_boundaries' INTO boundary_mode FROM catalog.quality_result
        WHERE release_id=NEW.id AND check_name='boundary_hierarchy' AND passed;
    IF boundary_mode IS NULL OR boundary_mode NOT IN ('source','union_of_children') THEN
        RAISE EXCEPTION 'Missing boundary hierarchy policy';
    END IF;
    IF EXISTS (
        SELECT 1 FROM geo.boundary b
        JOIN geo.territory t ON t.id=b.territory_id
        JOIN geo.territory pt ON pt.id=t.parent_id
        LEFT JOIN geo.boundary p ON p.release_id=b.release_id AND p.territory_id=pt.id
        WHERE b.release_id=NEW.id AND pt.level<>'country' AND (
          p.territory_id IS NULL OR
          CASE WHEN ST_CoveredBy(b.geom,p.geom) THEN false
               WHEN boundary_mode='union_of_children' THEN true
               ELSE coalesce(ST_Area(ST_Difference(b.geom,p.geom)::geography)
                    / NULLIF(ST_Area(b.geom::geography),0),1)>0.02 END)
    ) THEN RAISE EXCEPTION 'Boundary hierarchy changed before publication'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER geographic_evidence_publication BEFORE INSERT OR UPDATE ON catalog.release
FOR EACH ROW WHEN (NEW.publication_kind='coverage')
EXECUTE FUNCTION catalog.recheck_geographic_evidence();

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
