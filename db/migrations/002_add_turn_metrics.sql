ALTER TABLE results
    ADD COLUMN turn_times TEXT;

ALTER TABLE results
    ADD COLUMN approach_times TEXT;

ALTER TABLE results
    ADD COLUMN underwater_times TEXT;

CREATE TABLE IF NOT EXISTS turn_analysis (
    id INTEGER PRIMARY KEY,
    result_id INTEGER NOT NULL,
    turn_number INTEGER NOT NULL,
    approach_time REAL,
    wall_contact_time REAL,
    push_off_time REAL,
    underwater_time REAL,
    total_turn_time REAL,
    FOREIGN KEY (result_id) REFERENCES results(id)
);

CREATE INDEX IF NOT EXISTS idx_turn_analysis_result_id
    ON turn_analysis(result_id);

CREATE INDEX IF NOT EXISTS idx_turn_analysis_result_turn
    ON turn_analysis(result_id, turn_number);

CREATE INDEX IF NOT EXISTS idx_turn_analysis_turn_number
    ON turn_analysis(turn_number);
