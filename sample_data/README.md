# SmartSlot CSV template

SmartSlot imports a college timetable from **eight CSV files** (seven required, one
optional). Blank header-only copies are in [`templates/`](templates/); ready-made
datasets are in `feasible/`, `infeasible/` and `invalid/`.

| File | Required | One row per |
|------|----------|-------------|
| `teachers.csv` | yes | teacher |
| `subjects.csv` | yes | subject |
| `batches.csv` | yes | student batch (class section) |
| `rooms.csv` | yes | room |
| `requirements.csv` | yes | (subject, batch, teacher) weekly requirement |
| `days.csv` | yes | working day |
| `periods.csv` | yes | period (teaching period **or** break) |
| `availability.csv` | optional | (resource, day, period) the resource is *not* available |

General rules
* UTF-8, comma separated, first line is the header (exact column names, any order).
* Blank lines are ignored; surrounding spaces are trimmed; IDs are case-sensitive.
* **Row numbers in error messages are spreadsheet rows**: the header is row 1, the
  first data row is row 2.
* All `*_id` values must be unique inside their file.
* Booleans accept `1/0`, `true/false`, `yes/no` (any case).

---

## teachers.csv
| Column | Type | Required | Rules |
|--------|------|----------|-------|
| `teacher_id` | text | yes | unique, e.g. `T01` |
| `name` | text | yes | shown in the timetable, e.g. `Dr. Sharma` |
| `department_id` | text | no | e.g. `CE` |

## subjects.csv
| Column | Type | Required | Rules |
|--------|------|----------|-------|
| `subject_id` | text | yes | unique, e.g. `CS201` |
| `name` | text | yes | e.g. `Data Structures` |
| `department_id` | text | no | |
| `session_type` | `lecture` \| `practical` | yes | `practical` subjects can only be placed in a **lab**, `lecture` subjects only in a **classroom** |

## batches.csv
| Column | Type | Required | Rules |
|--------|------|----------|-------|
| `batch_id` | text | yes | unique, e.g. `CE-A` |
| `name` | text | yes | shown in the timetable (usually the same as `batch_id`) |
| `semester` | text | no | e.g. `3` |
| `student_count` | whole number >= 1 | yes | a room must seat at least this many students |
| `department_id` | text | no | |

## rooms.csv
| Column | Type | Required | Rules |
|--------|------|----------|-------|
| `room_id` | text | yes | unique, e.g. `R101`, `LAB1` |
| `name` | text | yes | e.g. `Room 101` |
| `capacity` | whole number >= 1 | yes | seats |
| `room_type` | `classroom` \| `lab` | yes | |

## requirements.csv
One row per subject taught to a batch by a teacher. A row with
`sessions_per_week = 4` becomes 4 sessions with ids `<subject>-<batch>-1` ...
`<subject>-<batch>-4` (e.g. `CS201-CE-A-1`).

| Column | Type | Required | Rules |
|--------|------|----------|-------|
| `subject_id` | text | yes | must exist in `subjects.csv` |
| `batch_id` | text | yes | must exist in `batches.csv` |
| `teacher_id` | text | yes | must exist in `teachers.csv` |
| `sessions_per_week` | whole number >= 1 | yes | sessions to place each week |
| `duration` | whole number >= 1 | no (default `1`) | **consecutive periods** per session; practicals are usually `2`. A multi-period session may not span a break |

Each (`subject_id`, `batch_id`, `teacher_id`) combination may appear only once.

## days.csv
Single column `day` listing the working days in order, using `Mon Tue Wed Thu Fri Sat Sun`
(each at most once). Add `Sat` to run a six-day week.

## periods.csv
Defines the time grid. **A break is a period row with `is_break = 1`.**

| Column | Type | Required | Rules |
|--------|------|----------|-------|
| `period` | whole number >= 1 | yes | unique, increasing; periods are numbered in time order |
| `start` | `HH:MM` (24h) | yes | |
| `end` | `HH:MM` (24h) | yes | later than `start` |
| `is_break` | boolean | no (default `0`) | a break can never hold a class and **a multi-period session can never span it** |

**Break / period numbering decision.** A lunch break is its own numbered row. The
demo day has periods `1 2 3`, a lunch row `4` (`is_break=1`), and periods `5 6 7`:
six *teaching* periods per day, seven rows in the grid. Messages therefore say
"Period 5" for the first class after lunch. The UI should draw break rows shaded
and unlabeled by a class. Because the break has its own number, a 2-period practical
starting in Period 3 is rejected ("cannot run across Period 4, a break"), while
Periods 5-6 or 1-2 are fine.

## availability.csv (optional)
Lists the slots a teacher **or** room is **not** available. Everything not listed is
available (the default), so you only list exceptions.

| Column | Type | Required | Rules |
|--------|------|----------|-------|
| `resource_id` | text | yes | a `teacher_id` or a `room_id` that exists |
| `day` | `Mon`..`Sun` | yes | must be listed in `days.csv` |
| `period` | whole number | yes | must exist in `periods.csv` |
| `available` | boolean | yes | `0`/`no`/`false` = **not available** (this is what you normally write). Rows with `1`/`yes`/`true` are accepted and ignored because available is already the default |

Example: Dr. Sharma is away on Monday Period 3 -> `T01,Mon,3,0`. To block a whole
afternoon list each period: `T01,Fri,5,0`, `T01,Fri,6,0`, `T01,Fri,7,0`.

---

## Hard rules the scheduler enforces
A teacher, a batch and a room can each be in only one place at a time; teachers and
rooms are never used while marked unavailable; `room.capacity >= batch.student_count`;
practicals use labs and lectures use classrooms; every session occupies `duration`
consecutive teaching periods with no break in between and stays inside the working
day.

## The three demo datasets
| Folder | What it is | Expected result |
|--------|------------|-----------------|
| `feasible/` | PRD section 16 demo: 6 teachers, 5 subjects, 3 batches, 4 rooms (3 classrooms + 1 lab), Mon-Fri, 6 teaching periods + lunch | **Complete**, 60 of 60 sessions, 0 conflicts |
| `infeasible/` | Same data, but DS Lab is required **4x per week** per batch | **Partial**, 63 of 66 scheduled; see [`infeasible/EXPECTED_RESULT.md`](infeasible/EXPECTED_RESULT.md) |
| `invalid/` | Same shape with 35 deliberate data errors | Import rejected with row-level errors; see [`invalid/EXPECTED_ERRORS.md`](invalid/EXPECTED_ERRORS.md) |

### What is in `feasible/` (so the demo story is predictable)
* **Rooms**: Room 101 seats 65, Room 102 seats 58, Room 103 seats 48, Computer Lab 1 seats 70.
  CE-A (60) fits only Room 101; CE-B (55) fits Rooms 101-102; CE-C (45) fits any classroom.
  Room 103 is too small for CE-A and CE-B. Practicals (DS Lab, 2 periods, twice a week per
  batch) can only go in Computer Lab 1.
* **Unavailability**: Dr. Sharma - Monday Period 3 and Friday afternoon (Periods 5-7);
  Prof. Iyer - Wednesday Period 7; Dr. Mehta - Thursday Periods 1-2; Mr. Das and
  Computer Lab 1 - Wednesday afternoon (Periods 5-7).
* **Teachers**: Dr. Sharma (Data Structures, CE-A/CE-B), Dr. Rao (Data Structures and DBMS,
  CE-C), Dr. Mehta (DBMS, CE-A/CE-B), Ms. Kapoor (Operating Systems, all), Prof. Iyer
  (Engineering Maths, all), Mr. Das (DS Lab, all).

## How to fix common import errors
| Message | Fix |
|---------|-----|
| *missing required field* | Fill the empty cell (see "Required" above). |
| *duplicate identifier* | Two rows share an id; change one (the first row keeps the id). |
| *not a whole number* / *out of range* | Use digits only, and 1 or more (`capacity`, `student_count`, `sessions_per_week`, `duration`, `period`). |
| *invalid value for room_type / session_type* | Use exactly `classroom`/`lab` or `lecture`/`practical`. |
| *reference to nonexistent teacher / subject / batch / room* | Add the missing record to its file or correct the id in `requirements.csv` / `availability.csv`. |
| *invalid day name* | Use `Mon Tue Wed Thu Fri Sat Sun`; days not in `days.csv` cannot be used in `availability.csv`. |
| *period not in periods.csv* | Use a period number that exists, or add it to `periods.csv`. |
| *invalid time* / *end not after start* | Use 24-hour `HH:MM`, with `end` later than `start`. |
| *duplicate requirement* | Merge into one row and add the `sessions_per_week` together. |
