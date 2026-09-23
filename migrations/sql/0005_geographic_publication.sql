-- Recheck current draft evidence, not just the state seen when rows were inserted.
-- Published releases are not rewritten or reclassified by this migration.
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
    -- Merger/split cardinalities remain enforced by coverage_publication (0003).
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
