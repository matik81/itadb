-- Append-only display cartography, tied to the snapshot's existing source archive.
CREATE TABLE population.province (
    snapshot_id bigint NOT NULL REFERENCES population.snapshot(id),
    code smallint NOT NULL CHECK (code BETWEEN 1 AND 999),
    region_code smallint NOT NULL,
    name text NOT NULL,
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[a-f0-9]{64}$'),
    boundary geometry(MultiPolygon,4326) NOT NULL,
    PRIMARY KEY(snapshot_id,code),
    CHECK (ST_IsValid(boundary) AND NOT ST_IsEmpty(boundary))
);
CREATE FUNCTION population.guard_province() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP<>'INSERT' THEN
        RAISE EXCEPTION 'Published cartography is immutable';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM population.municipality
        WHERE snapshot_id=NEW.snapshot_id AND province_code=NEW.code
        AND region_code=NEW.region_code AND province_name=NEW.name
    ) OR NOT EXISTS (
        SELECT 1 FROM population.snapshot s,
        jsonb_array_elements(s.provenance->'sources') source
        WHERE s.id=NEW.snapshot_id AND source->>'group'='national'
        AND source->>'name'='geography' AND source->>'sha256'=NEW.source_sha256
    ) THEN
        RAISE EXCEPTION 'Province differs from snapshot geography or provenance';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER province_guard BEFORE INSERT OR UPDATE OR DELETE ON population.province
FOR EACH ROW EXECUTE FUNCTION population.guard_province();
CREATE TRIGGER province_truncate_guard BEFORE TRUNCATE ON population.province
FOR EACH STATEMENT EXECUTE FUNCTION population.guard_province();
REVOKE ALL ON FUNCTION population.guard_province() FROM PUBLIC;
CREATE VIEW api.population_provinces AS SELECT p.* FROM population.province p
JOIN population.snapshot s ON s.id=p.snapshot_id AND s.status='published';
