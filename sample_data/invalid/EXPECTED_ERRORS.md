# Expected errors in `sample_data/invalid/`

Every file in this folder is a copy of the demo data with **deliberate** mistakes.
The importer must report each error below (and nothing silently discarded). The
valid rows around them must still be accepted so the user can see what is fine.

**Row numbers** are spreadsheet rows: the header is row 1, the first data row is
row 2. Rows not listed here are valid.

Valid reference data in this folder (so reference checks are meaningful):
teachers `T01 T02 T03 T04`, subjects `CS201 CS202 MA201 CS291`, batches `CE-A CE-B`,
rooms `R101 R102 LAB1`, days `Mon..Fri`, periods `1..7` (4 = lunch break).

## Errors (all severity = error; generation must be blocked)

| # | File | Row | Field | Value | Error class | Why / how to fix |
|---|------|-----|-------|-------|-------------|------------------|
| 1 | teachers.csv | 6 | teacher_id | `T03` | duplicate identifier | Already used by Dr. Mehta (row 4). Give the new teacher a unique id. |
| 2 | teachers.csv | 7 | name | *(empty)* | missing required field | Fill in the teacher's name. |
| 3 | teachers.csv | 8 | teacher_id | *(empty)* | missing required field | Every teacher needs an id. |
| 4 | subjects.csv | 6 | session_type | `seminar` | invalid allowed value | Use `lecture` or `practical`. |
| 5 | subjects.csv | 7 | subject_id | `CS202` | duplicate identifier | Already used by DBMS (row 3). |
| 6 | batches.csv | 4 | student_count | `abc` | not a whole number | Enter the number of students, e.g. `45`. |
| 7 | batches.csv | 5 | student_count | `-5` | number out of range | Must be 1 or more. |
| 8 | batches.csv | 6 | batch_id | `CE-A` | duplicate identifier | Already used in row 2. |
| 9 | batches.csv | 7 | name | *(empty)* | missing required field | Fill in the batch name. |
| 10 | rooms.csv | 5 | capacity | `abc` | not a whole number | Enter the number of seats. |
| 11 | rooms.csv | 6 | room_type | `auditorium` | invalid allowed value | Use `classroom` or `lab`. |
| 12 | rooms.csv | 7 | room_id | `R101` | duplicate identifier | Already used in row 2. |
| 13 | rooms.csv | 8 | capacity | `0` | number out of range | Must be 1 or more. |
| 14 | requirements.csv | 6 | teacher_id | `T99` | reference to nonexistent teacher | Add `T99` to teachers.csv or fix the id. |
| 15 | requirements.csv | 7 | subject_id | `XX999` | reference to nonexistent subject | Add the subject or fix the id. |
| 16 | requirements.csv | 8 | batch_id | `CE-Z` | reference to nonexistent batch | Add the batch or fix the id. |
| 17 | requirements.csv | 9 | sessions_per_week | `0` | number out of range | Must be 1 or more. |
| 18 | requirements.csv | 10 | sessions_per_week | `four` | not a whole number | Enter digits, e.g. `4`. |
| 19 | requirements.csv | 11 | duration | `two` | not a whole number | Enter the number of consecutive periods, e.g. `2`. |
| 20 | requirements.csv | 12 | subject_id | *(empty)* | missing required field | Every requirement needs a subject. |
| 21 | requirements.csv | 13 | duration | `0` | number out of range | Must be 1 or more. |
| 22 | requirements.csv | 14 | subject_id + batch_id + teacher_id | `CS201 / CE-A / T01` | duplicate requirement | Same as row 2; it would double the weekly sessions. Delete or merge it. |
| 23 | availability.csv | 5 | resource_id | `T77` | reference to nonexistent teacher/room | `resource_id` must be a teacher_id or room_id. |
| 24 | availability.csv | 6 | day | `Funday` | invalid day name | Use `Mon Tue Wed Thu Fri Sat Sun`. |
| 25 | availability.csv | 7 | day | `Sat` | day not in days.csv | Add `Sat` to days.csv or delete the row. |
| 26 | availability.csv | 8 | period | `15` | period not in periods.csv | Use a period number defined in periods.csv. |
| 27 | availability.csv | 9 | period | `abc` | not a whole number | Enter the period number. |
| 28 | availability.csv | 10 | available | `maybe` | invalid allowed value | Use `1/0`, `yes/no` or `true/false`. |
| 29 | days.csv | 7 | day | `Tue` | duplicate day | Each working day may be listed once. |
| 30 | days.csv | 8 | day | `Holiday` | invalid day name | Use `Mon Tue Wed Thu Fri Sat Sun`. |
| 31 | periods.csv | 9 | period | `3` | duplicate period number | Already defined in row 4. |
| 32 | periods.csv | 10 | start | `9am` | invalid time format | Use 24-hour `HH:MM`, e.g. `09:00`. |
| 33 | periods.csv | 11 | end | `16:40` | end not after start | `start` is `17:30`; end must be later than start. |
| 34 | periods.csv | 12 | is_break | `maybe` | invalid allowed value | Use `1/0`, `yes/no` or `true/false`. |
| 35 | periods.csv | 13 | period | `x` | not a whole number | Enter the period number. |

**Total: 35 deliberate errors** (3 teachers, 2 subjects, 4 batches, 4 rooms,
9 requirements, 6 availability, 2 days, 5 periods).

Notes for the importer author:
* If a row ever carries more than one problem, report every problem, not just the first.
  (Here each bad row has exactly one problem, so the expected count is exact.)
* Rows that fail are rejected, not repaired; later rows that reference a rejected
  row (e.g. an id that only exists in a rejected row) will legitimately raise
  reference errors too. The rows above were chosen so that no such cascade occurs.
* The first occurrence of a duplicated id (teachers row 4, subjects row 3, batches
  row 2, rooms row 2, requirements row 2, days row 3, periods row 4) is the valid one.
