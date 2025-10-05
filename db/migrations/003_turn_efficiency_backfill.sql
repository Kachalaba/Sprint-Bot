-- Fill missing total turn times for historical breaststroke and butterfly entries.
BEGIN TRANSACTION;

UPDATE turn_analysis
SET total_turn_time = ROUND(
        COALESCE(approach_time, 0)
        + COALESCE(wall_contact_time, 0)
        + COALESCE(push_off_time, 0)
        + COALESCE(underwater_time, 0),
        3
    )
WHERE (total_turn_time IS NULL OR total_turn_time <= 0)
  AND result_id IN (
        SELECT id FROM results WHERE LOWER(stroke) IN ('breaststroke', 'butterfly')
    );

COMMIT;
