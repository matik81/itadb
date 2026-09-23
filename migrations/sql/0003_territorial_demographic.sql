ALTER TABLE catalog.release ADD COLUMN publication_kind text NOT NULL DEFAULT 'legacy'
    CHECK (publication_kind IN ('legacy','coverage'));
ALTER TABLE catalog.artifact DROP CONSTRAINT artifact_kind_check,
    ADD CONSTRAINT artifact_kind_check CHECK (kind IN
        ('raw','curated','quality','structure','dataflow','contract','onboarding_contract',
         'data_manifest','structure_manifest','dataflow_manifest','license','onboarding',
         'evidence','geography','crosswalk'));

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

CREATE OR REPLACE FUNCTION stats.check_observation_context() RETURNS trigger LANGUAGE plpgsql AS $$
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

-- Keep the proven M1 gate, adding a separate coverage publication gate.
ALTER FUNCTION catalog.check_release_publication() RENAME TO check_legacy_release_publication;
DROP TRIGGER release_publication ON catalog.release;
CREATE TRIGGER release_publication BEFORE INSERT OR UPDATE ON catalog.release
FOR EACH ROW WHEN (NEW.publication_kind='legacy')
EXECUTE FUNCTION catalog.check_legacy_release_publication();

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
