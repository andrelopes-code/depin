# Performance

`depin` sits on application construction and resolution paths. Some of those run
once at startup; others run on every request. Whether that matters depends on
what your providers do and how often you resolve, and no benchmark can answer
that for your application.

What this section can do is make the cost knowable: what each operation costs
here, how much of that is `depin` rather than the work it was asked to do, how it
scales, and where it stops being measurable at all.

## Where the numbers are

- **[Results](results.md)** — the measured figures, separated into startup and
  recurring costs, each against a direct-Python baseline. That page is generated
  from the committed dataset, so it cannot drift from its evidence.
- **[Methodology](methodology.md)** — how the numbers are produced, and what
  would make them wrong.
- **[Reproducing](reproducing.md)** — the commands to run all of it yourself.

## How to read any figure here

**Absolute times are host-specific.** They were measured on a documented
developer workstation, not a dedicated benchmark machine, because the project
does not own one. What transfers to your hardware is the ratio to the direct
baseline, the shape of the scaling curves, and the deterministic counts — not the
microseconds.

**Startup and per-request costs are different things.** Validating a graph
happens once per process. Resolving a cached singleton can happen thousands of
times per second. They are never combined into one score, and a number from one
says nothing about the other.

**Overhead is the difference from doing the same work by hand.** Every workload
is paired with the simplest honest Python that produces the same result — direct
attribute access, explicit construction, a handwritten context manager, the same
FastAPI application wired manually. The pair is proved to do the same thing by an
ordinary test before either side is timed.

**Where the overhead is smaller than the measurement noise, that is what is
reported** — not that it was zero.

## Estimating your own case

The useful question is not what a resolution costs but whether that cost is
visible next to your provider work. The per-operation figures on the results page
can be turned into a rate: an operation costing *c* microseconds, performed *n*
times per request at *r* requests per second, consumes `c × n × r` microseconds of
CPU per second — divide by a million for the fraction of one core.

That arithmetic is honest only as far as its assumptions. Provider work, graph
shape, contention, hardware, interpreter version and framework behaviour all move
the result, and an application whose endpoints touch a database or a network is
usually dominated by that rather than by wiring.

## What this section will not claim

There is no overall score here, no league table, and no claim that `depin` is the
fastest dependency-injection library for Python. Results are per workload,
carrying their baseline and their uncertainty. Where two libraries cannot be made
to do observably the same thing, the workload is labelled incomparable rather than
counted as a win — and unfavourable `depin` results are published under exactly
the same rules as favourable ones.

Comparisons with other libraries are not published yet. The eligibility screen has
been run and recorded; the comparison page is deliberately left until the
methodology has been exercised on `depin` alone.
