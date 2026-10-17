# Why `sample_data/infeasible/` cannot be fully scheduled

This dataset is `feasible/` with **one change**: in `requirements.csv` the DS Lab
(`CS291`, taught by Mr. Das, 2 consecutive periods, practical => lab only) is required
**4 times per week for every batch** instead of 2.

```
CS291,CE-A,T05,4,2     (was 2)
CS291,CE-B,T05,4,2     (was 2)
CS291,CE-C,T05,4,2     (was 2)
```

That is **12 two-period lab sessions** per week. Everything else is identical.

## Why it is impossible (provable by counting)
* There is exactly one lab, **Computer Lab 1**. A two-period practical needs two
  consecutive teaching periods; each day has two such blocks (Periods 1-3 -> one block,
  Periods 5-7 -> one block, because lunch is Period 4). Over Mon-Fri that is 10 blocks,
  and the lab is under maintenance on **Wednesday afternoon** (Periods 5-7), leaving
  **9 blocks per week**.
* Mr. Das, the only DS Lab teacher, is also unavailable Wednesday afternoon, so he can
  also teach in at most **9 blocks**.
* 12 sessions > 9 blocks, so at least **3** DS Lab sessions can never be scheduled, no
  matter how the rest is arranged. (Total lab periods needed: 24 of the 27 free lab
  periods looks feasible by period count alone - the *consecutive-block* limit is what
  makes it impossible, and it is exactly the kind of rule a spreadsheet misses.)

## Expected engine result
* `status = "partial"`: **63 of 66** sessions scheduled, 3 unscheduled, 0 hard conflicts
  among the scheduled ones, no search limit hit (`hit_limit = false`).
* Unscheduled: the last DS Lab session of each batch (spreading the shortfall fairly):
  `CS291-CE-A-4`, `CS291-CE-B-4`, `CS291-CE-C-4`.
* Findings / reasons shown for each (wording may vary slightly):
  * "Mr. Das needs 12 sessions of 2 or more consecutive periods per week, but only 9 such
    blocks fit in the periods Mr. Das is available."
  * "The laboratory (Computer Lab 1) can fit at most 9 blocks of 2 consecutive periods per
    week, but 12 such laboratory sessions are required."
* Fix hints: reduce the DS Lab sessions per week (back to 2 per batch makes it feasible),
  add another lab, or free up Computer Lab 1 / Mr. Das on Wednesday afternoon.
