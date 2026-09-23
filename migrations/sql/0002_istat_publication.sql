CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE catalog.release
    ADD COLUMN api_version smallint NOT NULL DEFAULT 1 CHECK (api_version IN (1,2)),
    ADD COLUMN metadata_sha256 text NOT NULL DEFAULT repeat('0',64)
        CHECK (metadata_sha256 ~ '^[a-f0-9]{64}$'),
    ADD COLUMN upstream_last_update timestamptz,
    ADD COLUMN upstream_published_at timestamptz,
    ADD COLUMN supersedes_release_id uuid,
    ADD COLUMN revision_reason text,
    ADD COLUMN territory_snapshot date,
    ADD COLUMN series_code text NOT NULL DEFAULT 'population_total' REFERENCES stats.series(code),
    ADD COLUMN attribution text,
    ADD CONSTRAINT release_revision_identity UNIQUE (id,dataset_id,reference_period),
    ADD CONSTRAINT release_predecessor FOREIGN KEY
        (supersedes_release_id,dataset_id,reference_period)
        REFERENCES catalog.release(id,dataset_id,reference_period),
    ADD CONSTRAINT release_revision_reason CHECK (
        (supersedes_release_id IS NULL AND revision_reason IS NULL) OR
        (supersedes_release_id IS NOT NULL AND revision_reason IS NOT NULL
         AND length(trim(revision_reason)) BETWEEN 1 AND 1000 AND supersedes_release_id <> id)
    );
ALTER TABLE catalog.release
    DROP CONSTRAINT release_dataset_id_raw_sha256_transform_version_contract_sh_key,
    ADD CONSTRAINT release_content_identity UNIQUE
        (dataset_id,raw_sha256,transform_version,contract_sha256,metadata_sha256);
CREATE UNIQUE INDEX release_one_successor ON catalog.release(supersedes_release_id)
    WHERE supersedes_release_id IS NOT NULL;
CREATE UNIQUE INDEX release_one_v2_root ON catalog.release(dataset_id,reference_period)
    WHERE api_version=2 AND supersedes_release_id IS NULL;

ALTER TABLE catalog.artifact DROP CONSTRAINT artifact_kind_check,
    ADD CONSTRAINT artifact_kind_check CHECK (kind IN
        ('raw','curated','quality','structure','dataflow','contract','onboarding_contract',
         'data_manifest','structure_manifest','dataflow_manifest','license','onboarding'));
ALTER TABLE geo.territory ADD CONSTRAINT territory_no_overlap
    EXCLUDE USING gist (scheme WITH =, code WITH =,
        daterange(valid_from,valid_to,'[)') WITH &&);

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

ALTER TABLE stats.observation DROP CONSTRAINT observation_status_check,
    ADD CONSTRAINT observation_status_check CHECK
        (status IN ('observed','estimated','missing','suppressed','demo','unflagged_upstream')),
    ADD COLUMN upstream_status text NOT NULL DEFAULT '',
    ADD COLUMN upstream_note text NOT NULL DEFAULT '',
    ADD COLUMN upstream_unit text NOT NULL DEFAULT '',
    ADD COLUMN upstream_unit_multiplier text NOT NULL DEFAULT '';

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
       (release.api_version=2 AND
        (NEW.period<>release.reference_period OR NOT EXISTS
         (SELECT 1 FROM stats.series WHERE id=NEW.series_id AND code=release.series_code))) THEN
        RAISE EXCEPTION 'Observation is incompatible with its release';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER observation_context BEFORE INSERT OR UPDATE ON stats.observation
FOR EACH ROW EXECUTE FUNCTION stats.check_observation_context();

CREATE FUNCTION catalog.check_release_publication() RETURNS trigger LANGUAGE plpgsql AS $$
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
FOR EACH ROW EXECUTE FUNCTION catalog.check_release_publication();

-- Original v1 columns and enum remain unchanged. Official releases use v2.
CREATE OR REPLACE VIEW api.releases AS
SELECT r.id, r.dataset_id, d.title, d.limitations, d.source_id, s.is_demo,
       r.reference_period, r.retrieved_at, r.published_at, r.upstream_url,
       r.raw_sha256, r.transform_version, r.contract_sha256, r.license_url, r.row_count
FROM catalog.release r JOIN catalog.dataset d ON d.id=r.dataset_id
JOIN catalog.source s ON s.id=d.source_id WHERE r.status='published' AND r.api_version=1;
CREATE OR REPLACE VIEW api.observations AS
SELECT o.release_id, s.code AS series_code, s.unit, t.id AS territory_id,
       t.code AS territory_code, t.name AS territory_name, t.scheme,
       o.period, o.value, o.status
FROM stats.observation o JOIN catalog.release r
    ON r.id=o.release_id AND r.status='published' AND r.api_version=1
JOIN stats.series s ON s.id=o.series_id JOIN geo.territory t ON t.id=o.territory_id;
CREATE OR REPLACE VIEW api.quality AS
SELECT q.release_id, q.check_name, q.passed, q.details FROM catalog.quality_result q
JOIN catalog.release r ON r.id=q.release_id WHERE r.status='published' AND r.api_version=1;

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
