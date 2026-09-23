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
