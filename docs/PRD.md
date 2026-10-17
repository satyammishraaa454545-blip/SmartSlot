# SmartSlot — Product Requirements Document

## 1. Product Vision

SmartSlot is a teacher-friendly college timetable scheduling application that generates valid timetables from college ERP data while preventing teacher, classroom, and student-batch scheduling conflicts.

The system must explain scheduling problems in simple language, help coordinators resolve them, and allow them to publish a verified timetable.

**Product promise:** Create a workable timetable without overlapping classes, double-booked rooms, or double-booked teachers.

## 2. Problem Statement

Colleges often create timetables manually using spreadsheets, documents, and repeated coordination between departments.

This can lead to:
- A teacher assigned to two classes at the same time.
- A classroom assigned to multiple classes simultaneously.
- A student batch scheduled for two lectures at once.
- Practical sessions assigned to unsuitable rooms.
- Uneven teaching loads and inconvenient schedules.
- Errors introduced while editing or swapping periods.
- Time-consuming revisions when a teacher or room becomes unavailable.

The challenge is not merely displaying a timetable. It is producing a valid timetable that satisfies college rules and remains valid when changes are made.

## 3. Proposed Solution

SmartSlot imports structured timetable information from the college ERP or a sample ERP export, validates the data, generates a conflict-free schedule, and provides a visual interface for reviewing and editing it.

The coordinator can:
1. Import teachers, subjects, batches, rooms, and lecture requirements.
2. Define working days, periods, availability, and scheduling rules.
3. Generate a timetable automatically.
4. Review conflicts and understand why a session could not be scheduled.
5. Make changes through a controlled timetable editor.
6. Validate the complete timetable again.
7. Publish or export the approved timetable.

## 4. Target Users

### Primary: Timetable Coordinator
Needs to prepare and revise timetables without manually checking every teacher, room, and batch.

### Secondary: Faculty Member
Needs to see their own schedule and avoid overlapping assignments.

### Secondary: Department Head
Needs to review workload distribution, room usage, and department schedules.

### Optional: Student
Needs a clear view of the timetable for their batch.

The hackathon MVP prioritizes the timetable coordinator. Other roles can have read-only views.

## 5. Product Goals

- Generate a valid timetable from a small, realistic college dataset.
- Prevent teacher, room, and batch clashes.
- Respect teacher availability and subject-room requirements.
- Explain unscheduled sessions and scheduling failures.
- Detect conflicts immediately after timetable edits.
- Provide a polished, easy-to-understand interface.
- Demonstrate the workflow using college ERP-format data.

### Success metrics for the MVP

- Zero hard-constraint conflicts in every successfully generated timetable.
- Every required session is scheduled, or explicitly reported as unscheduled.
- Every manual edit is revalidated before it can be published.
- A coordinator can complete the sample demo workflow without technical assistance.
- Invalid input produces understandable error messages instead of silent failures.

## 6. Scope and Priorities

### P0 — Must have

- Sample ERP data import through CSV.
- Validation of teachers, subjects, batches, rooms, and lecture requirements.
- Working-day and period configuration.
- Teacher availability.
- Room capacity and room type requirements.
- Automatic timetable generation.
- Teacher, room, and batch clash prevention.
- Visual timetable grid.
- Conflict explanations.
- Manual editing with revalidation.
- Publish and export timetable.
- Demo-ready sample dataset.

### P1 — Strong differentiators

- Compare the current and proposed timetable.
- Show which classes are affected by a change.
- Show teacher workload and room utilization.
- Provide a suggested alternative slot for a failed scheduling request.
- Save timetable versions and revert to a previous version.
- Display unscheduled sessions in a dedicated panel.

### P2 — Future enhancements

- Direct ERP API synchronization.
- Multiple departments and campuses.
- Automatic substitution for absent faculty.
- Notifications for timetable changes.
- Student portal and mobile application.
- Advanced optimization for teacher preferences.

Do not implement P2 before the complete P0 workflow works reliably.

## 7. Core User Journey

1. The coordinator opens SmartSlot.
2. They select the semester and upload the ERP timetable data.
3. SmartSlot validates the data and highlights missing or inconsistent records.
4. The coordinator confirms the available days, periods, rooms, and teacher availability.
5. They click Generate Timetable.
6. SmartSlot produces a timetable and checks all hard constraints.
7. The coordinator reviews unscheduled sessions, if any.
8. They edit or regenerate the schedule when necessary.
9. SmartSlot validates all changes.
10. The coordinator publishes the timetable and exports it as CSV or PDF.

## 8. Functional Requirements

### FR-01: ERP Data Import

The system must accept a documented CSV template containing the required scheduling data.

Minimum entities:
- Teachers
- Subjects and required weekly sessions
- Student batches
- Rooms and capacities
- Practical or lecture requirements
- Teacher availability
- Working days and periods

The application must:
- Validate required fields.
- Reject invalid or duplicate identifiers.
- Detect references to nonexistent teachers, subjects, batches, or rooms.
- Show row-level errors and tell the user how to fix them.
- Avoid silently discarding invalid records.

For the hackathon, use a sample ERP export and a documented CSV template. Do not claim a live ERP integration unless an actual integration has been implemented and tested.

### FR-02: Scheduling Configuration

The coordinator can configure:
- Working days.
- Period start and end times.
- Breaks and unavailable periods.
- Teacher availability.
- Room capacity and room type.
- Required sessions per subject per week.
- Session duration.
- Batch and department requirements.

The initial version should support a fixed weekly timetable.

### FR-03: Automatic Generation

When the coordinator selects Generate Timetable, the system must:
- Find suitable slots for required sessions.
- Respect all hard constraints.
- Avoid placing a batch in two classes simultaneously.
- Avoid assigning a teacher to overlapping classes.
- Avoid double-booking rooms.
- Respect teacher availability and room suitability.
- Track scheduled and unscheduled sessions.
- Run a final validation before marking the schedule valid.

If a valid schedule cannot be found, the system must report the unscheduled sessions and the constraints that prevented placement.

It must never silently label an incomplete or invalid timetable as successfully generated.

### FR-04: Timetable Visualization

The coordinator can switch between:
- Batch-wise timetable.
- Teacher-wise timetable.
- Room-wise timetable.

The weekly grid must display:
- Subject.
- Teacher.
- Room.
- Batch.
- Period and time.

Use readable labels, clear empty slots, and visual distinction between scheduled and unscheduled sessions.

### FR-05: Conflict Detection

The system must check for:
- Teacher overlap.
- Room overlap.
- Batch overlap.
- Teacher unavailability.
- Insufficient room capacity.
- Incorrect room type.
- Invalid session duration.
- Sessions outside working hours.
- Missing required sessions.

Each conflict should explain the issue, for example:

"Dr. Sharma is already assigned to CE-A during Period 3 on Monday."

When possible, show the conflicting class and a suggested alternative slot.

### FR-06: Manual Editing

The coordinator can move a class to another slot or change its assigned room or teacher.

Before saving:
1. Validate the proposed change.
2. Identify all affected constraints.
3. Explain any blocking conflict.
4. Reject invalid changes or allow the coordinator to cancel.
5. Save valid changes and refresh the timetable.

The application must not allow an invalid change to become a published timetable.

### FR-07: Publishing and Export

The coordinator can:
- Review the final schedule.
- Publish a verified version.
- Export timetable data as CSV.
- Download or print a clean timetable PDF.

If any required session remains unscheduled, show a warning before publishing. For the MVP, incomplete schedules must not be marked fully complete.

## 9. Scheduling Rules

### Hard constraints — Must never be violated

1. A teacher cannot teach two classes in the same time slot.
2. A batch cannot attend two classes in the same time slot.
3. A room cannot host two classes in the same time slot.
4. A teacher cannot be assigned outside their availability.
5. A room must have sufficient capacity.
6. A room must support the session type.
7. A session must fit within working hours and respect blocked periods.
8. Every scheduled session must have valid teacher, subject, batch, and room references.
9. A session must occupy every period it requires without overlapping another session.
10. Every timetable edit must pass validation before publication.

### Soft constraints — Optimize when possible

- Distribute classes evenly across the week.
- Avoid excessive consecutive lectures for a teacher.
- Avoid unnecessary gaps in a teacher's schedule.
- Avoid unnecessarily early or late periods.
- Spread repeated sessions of a subject across different days.
- Respect teacher preferences where feasible.

Hard constraints determine validity. Soft constraints improve timetable quality and should never override a hard constraint.

## 10. Handling Important Edge Cases

### Teacher unavailable
Do not assign sessions during the unavailable period. If no suitable slot remains, report the unscheduled session.

### Room too small
Exclude the room from candidate slots and explain the capacity mismatch.

### Practical class needs a lab
Only consider rooms configured as compatible laboratories.

### No feasible slot exists
Keep the session in the unscheduled list and explain the blocking constraints.

### Duplicate ERP records
Flag duplicate identifiers and require correction before generation.

### Invalid teacher or room ID
Reject the affected record and display the relevant row and field.

### Two sessions require the same teacher and period
The scheduler must assign different periods or report that the requirements cannot all be satisfied.

### Manual swap creates a clash
Reject the invalid change and explain the conflict.

### Teacher becomes unavailable after generation
Mark the affected sessions for review. Revalidate before accepting a replacement schedule.

### User regenerates a timetable
Do not overwrite the last published timetable silently. Preserve the existing published version.

### Partial scheduling
Clearly distinguish scheduled sessions, unscheduled sessions, and a fully valid, complete timetable.

### Empty or incomplete dataset
Show validation errors and prevent generation until mandatory information is available.

### Multiple departments
Use department and semester identifiers to prevent unrelated records from being mixed. Resources shared across departments must still be checked globally.

## 11. Suggested Data Model

- Teacher: teacher_id, name, department_id.
- Subject: subject_id, name, department_id, session_type.
- Batch: batch_id, name, semester, student_count.
- Room: room_id, name, capacity, room_type.
- Availability: resource_id, day, period, available.
- SessionRequirement: subject_id, batch_id, teacher_id, sessions_per_week, duration.
- TimetableEntry: session_id, day, start_period, duration, teacher_id, room_id, subject_id, batch_id.
- TimetableVersion: version_id, status, created_at, created_by.

For the MVP, use a relational database such as SQLite or MySQL. The model should support unique IDs and reliable validation.

## 12. Scheduling Engine

Use a constraint-based backtracking scheduler for the initial implementation.

1. Expand weekly subject requirements into individual sessions.
2. Generate feasible candidate slots for each session.
3. Sort sessions by difficulty, placing the most constrained sessions first.
4. Try candidate slots in a sensible order.
5. Check hard constraints before assigning each session.
6. Backtrack when an assignment prevents the remaining sessions from being scheduled.
7. Stop when a complete valid schedule is found or the configured search limit is reached.
8. Validate the final timetable independently.
9. Return scheduled sessions, unscheduled sessions, and explanations.

Start with a small dataset and a clear search limit. Never present a search-limit result as proof that no feasible timetable exists; report that a solution was not found within the configured search limit.

## 13. Recommended Technical Architecture

Frontend:
- React.
- Tailwind CSS.
- A responsive timetable grid.

Backend:
- Python.
- FastAPI.
- Pydantic for request validation.

Database:
- SQLite for a quick hackathon MVP, or MySQL if the team already has a working setup.

Core modules:
- ERP import and validation.
- Scheduling engine.
- Conflict validator.
- Timetable editing and versioning.
- Export service.

Keep the scheduling engine independent from the user interface so it can be tested directly.

## 14. Non-Functional Requirements

- Clear, teacher-friendly language.
- Responsive layout for laptop and tablet.
- Useful loading and error states.
- No silent data loss.
- Consistent timetable validation.
- Basic input validation and secure file handling.
- Sample data available for offline demonstration.
- Deterministic, repeatable validation results.
- A published timetable must always pass the hard-constraint validator.

## 15. Acceptance Criteria

The MVP is ready to demonstrate when:

1. A coordinator can import the sample ERP dataset.
2. Invalid records are identified with actionable messages.
3. The scheduler can generate a complete timetable for the prepared feasible dataset.
4. No teacher, room, or batch overlaps exist in the generated timetable.
5. Room capacity, room type, and teacher availability are respected.
6. A deliberately impossible scheduling requirement is reported rather than silently ignored.
7. An invalid manual edit is rejected with an explanation.
8. A valid manual edit can be saved and revalidated.
9. The timetable can be viewed by teacher, room, and batch.
10. The coordinator can export and publish a verified timetable.
11. The previous published version remains recoverable.
12. The demo can run using a prepared local dataset without relying on a live ERP connection.

## 16. Demo Scenario

Use a small dataset with:
- 6 teachers.
- 5 subjects.
- 3 student batches.
- 4 classrooms, including one laboratory.
- 5 working days.
- 6 periods per day.

Create a scenario where a teacher is unavailable during one period and a practical session requires the laboratory.

Demo sequence:
1. Import the dataset.
2. Show the validation summary.
3. Generate the timetable.
4. Open the teacher-wise timetable.
5. Attempt an edit that creates a teacher clash.
6. Show SmartSlot blocking the change and explaining why.
7. Move the session to a valid slot.
8. Show the updated schedule and validation status.
9. Publish and export the timetable.

Prepare a separate deliberately infeasible test case to demonstrate the unscheduled-session explanation.

## 17. Risks and Mitigations

- Complex scheduling rules: begin with a small, explicit set of hard constraints.
- Large search space: use constrained-first ordering and a search limit.
- Messy ERP data: use a documented import template and row-level validation.
- Live ERP unavailable: demonstrate with a realistic sample export.
- Incomplete schedule mistaken for success: show completion status and unscheduled sessions prominently.
- Last-minute UI bugs: prioritize the complete happy path and one conflict-rejection flow.
- Team integration delays: define API contracts and test the scheduler independently.

## 18. Final Product Definition

SmartSlot is successful when a coordinator can import real-format college data, generate a valid weekly timetable, understand unresolved scheduling issues, safely revise the timetable, and publish a verified version without manually checking every possible clash.

The winning differentiation is not adding the largest number of features. It is demonstrating trustworthy scheduling, understandable conflict explanations, and a smooth coordinator workflow from import to publication.
