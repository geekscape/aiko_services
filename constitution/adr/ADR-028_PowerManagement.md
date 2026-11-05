---
title: "ADR-028 — Power management: the PowerManager Interface with one Implementation for each platform, a power hold that outlives its process, a release that happens only in the shutdown hook, and a quiesce mode before the power ends"
description: Makes host power a first-class Aiko Services concern. One
  Interface that extends Actor has one Implementation for each platform. It
  reports the supply and the battery, holds the power, signals, and reports
  the button. The hold does not use the GPIO character device, because that
  device releases the pin when the process exits. Only the shutdown hook
  releases the hold, and never on a restart. Before the power ends, the host
  synchronizes its file systems and tells its applications to stop writing,
  and at the floor voltage it remounts them read-only. The two privileged
  operations are granted explicitly and rendered before they are installed
type: adr
audience: [project-lead, architects, developers, ai-coding-agents]
status: proposal
ste: adapted
related: [ReadMe, ADR-022_CompositionBoundary, ADR-023_GuardedEvalDefaultDeny,
  ADR-025_RemoteDisplayAbstraction, ADR-026_DaemonSupervision,
  ../p_00_DesignPrinciples, ../p_02_CandidatePrinciples,
  ../s_02_InterfaceComposition]
last_updated: 2026-11-05
---

# ADR-028 — Power management: the `PowerManager` Interface with one Implementation for each platform, a power hold that outlives its process, a release that happens only in the shutdown hook, and a quiesce mode before the power ends

**Proposed 2026-11-05** by the power manager work, whose plan the technical lead reviewed on
2026-11-05. The number is claimed in this move. The reference implementation will be
`src/aiko_services/actors/power_manager/`.

## Context

A Device is a host that carries its own supply. It takes power from the platform that it
rides on, and it keeps a battery of its own. An operator switches the platform off at the end
of a working period, with no warning to the host.

Such a host records data and forwards it over an unreliable link. A power cut at the wrong
moment loses the record that is open. It can also corrupt the file system. The battery exists
so that the host finishes its work and then stops in an orderly manner.

A power management module answers this in hardware. It holds a battery and two power meters.
It also holds a battery temperature sensor, a buzzer, a button and a relay. The relay keeps
the host powered after the platform power stops. Shell scripts are enough to prove such a
board, and they are not enough to operate it: they carry no state, no policy, no test and no
report.

Four facts shaped this decision.

The same question appears away from the Device. A developer runs the same Actors on a Linux
laptop and on a MacBook, and both report a battery and a supply. A continuous integration
host reports neither. A design that works with one board only is a design that nobody can
test.

The Linux GPIO character device releases a line when the process that claimed it exits, and
the line returns to an input. `gpiozero`, `lgpio` and `libgpiod` all use it. Therefore a
long-lived Actor that held the relay pin would cut the power of a Device each time it
stopped, crashed or restarted. For this one pin, the safest component is the component that
is not running.

The release of the hold is the one operation that software cannot undo. After it, the host is
off. It must happen after the file systems are unmounted. It must not happen at all when the
operating system is restarting rather than stopping.

The battery is finite. Therefore every way that the power can end needs a window. In that
window the host stops writing and flushes what it holds. The power can end by an orderly
shutdown, by a battery that empties, or by a release that fails.

The project already has the shape for the first fact. `DaemonSupervisor` (ADR-026) is one
Interface with one Implementation for each platform, chosen by a `choose_*()` function.
`choose_output()` in the Display Actor does the same for display backends.

## Decision

1. **One `PowerManager` Interface, one Implementation for each platform.** The Interface
   declares `open`, `properties`, `sample`, `hold`, `signal`, `add_handler` and `close`. The
   Implementations are `PmmPowerManagerImpl` (a single-board computer with a power management
   module), `LinuxPowerManagerImpl` (`/sys/class/power_supply/`),
   `MacosPowerManagerImpl` (the operating system's own power tools) and
   `MockPowerManagerImpl`. `choose_power_manager()` selects one, in the way that
   `choose_daemon_supervisor()` does (P7). The mock is the registered default. Thus a platform
   with no Implementation reports itself, rather than doing something that cannot work.

   An aspect split, as ADR-025 made for the display, was considered and rejected for this
   subject. A display has three concerns that different clients use apart from each other. A
   host has one power facility, and what differs between platforms is how much of it is real.
   Property tokens carry that difference, and one Interface keeps the policy in one place.

2. **A property that a platform lacks is a no-op, not an error.** This is ADR-022 decision 1,
   and `NullOutputImpl` is the precedent. `properties()` returns the tokens that are real:
   `readings`, `hold`, `signal`, `button` and `dock`. The Actor advertises one Service tag for
   each property, such as `hold=true`, in the way that ADR-025 advertises the display aspects.
   One tag for each property is used, rather than one tag with a list. This avoids the
   `ServiceFilter` deviation, where a value that holds a space becomes two tags.

3. **`PowerReading` is a value type.** It is frozen, and a field that the platform does not
   measure is `None`. It takes the ADR-022 "value or data type" exemption.

4. **The Interface extends `Actor`, and each Implementation is the Actor.** `PowerManager`
   extends `Actor` and registers the protocol
   `github.com/geekscape/aiko_services/protocol/power_manager:0`. `ProcessManager` has this
   shape already, and the name follows it. The shared state, the sample timer, the log and the
   policy live in a plain mixin. The Implementations hold that mixin in common, and it is not
   a second Interface. `_Emulated` in the display outputs is the precedent.

5. **The power hold does not use the GPIO character device.** The hold is set and released by
   a short-lived helper that writes the pad registers and exits. The pin keeps its state,
   because nothing claims it.

   The hazard is the **clean** stop, and not the crash. A line claimed through the character
   device is released when it is closed. An orderly stop of a Service closes it, and so does
   the library as a process shuts down. A process that is killed may leave the pad driven
   instead. Both were measured on the hardware on 2026-11-05. A close returned the line to an
   input, and a kill left it an output. Thus a long-lived holder of this pin would release the
   power of an undocked Device when it was asked to stop politely. It would keep the power
   only when it died badly, and a design must not depend on that. On a single-board computer the helper runs the platform's own
   pin utility through a subprocess. This is a deliberate exception to "everything in
   Python", and the reason is recorded here: no character-device API can leave a pin driven
   after the process exits, so no such API can meet the safety rule. **The Actor never claims
   the hold pin.**

   The pin keeps its state across the exit of a process, and **not** across a reset of the
   board. A restart re-runs the platform firmware, which returns the pads to their default
   direction. Therefore the start-up operation of decision 9 re-asserts the hold on the way
   back up. A board that must survive a restart while it runs on its battery needs a relay
   that holds across that window. That is a property of the hardware, and this record does
   not claim it.

6. **Only the shutdown hook releases the hold.** The release happens in a shutdown hook of
   the operating system, after the file systems are unmounted. The hook reads the argument
   that the operating system passes it. It releases the hold when the host is stopping. It
   does nothing when the host is restarting, because a release there would stop a Device that
   is trying to come back. The hook waits a configured delay before the release, and the delay
   is never zero.

   This rule is necessary, and it is not enough on its own. Decision 5 records that a reset
   releases the hold by itself. Thus a host that must come back from a restart while undocked
   depends on its hardware as well as on this hook.

7. **A safe posture by default, and an unsafe posture by choice.** The Implementation takes
   `safe=SAFE`, where `SAFE` is true, in the way that `ProcessManagerImpl` does. `FUNCTIONS`
   declares what the Interface exposes, and `SAFE_FUNCTIONS` declares the subset that the safe
   posture allows: `sample` and `set_log_level`. The command line carries `--safe/--unsafe`,
   with `--safe` as the default. The posture is published as `safe` in the shared state, where
   it is a report and not a control. A request to change it from the message bus is denied,
   and the stored value is published again. A denial counts in `metrics.denied`.

   The wire surface is narrower than the Interface. The device seam acquires, reads and
   releases the hardware. It is named in one place and subtracted from the derived list.
   Thus the list still comes from the contract, and no lifecycle method is reachable from
   the bus. A test asserts the subtraction.

   `hold`, `shutdown`, `signal` and `set_period` are outside `SAFE_FUNCTIONS`. The first two
   stop a host. The other two look harmless, and the ProcessManager's rule applies: only a
   design and a test campaign make a function safe, not the observation that it looks
   harmless. A buzzer that any client can sound is a nuisance that reaches a person.
   `--unsafe` accepts every function that the Interface declares, which is appropriate only
   where the broker cannot be reached from outside a trusted network (ADR-023 decision 6).

8. **The policy is a pure function.** `decide()` takes a reading, the properties, the transfer
   queue state, the button state and the thresholds. It returns "hold", or a shutdown with one
   token that says why. It takes no device and no Actor, so a truth table tests every rule with
   no hardware. `classify()` in the WhisPlay button is the precedent.

9. **`render` before `install`.** ADR-026 decision 3 covers the unit that asserts the hold at
   start-up, and the shutdown hook of decision 6. `render()` returns the text and changes
   nothing. `install()` is the only operation that changes the host, it needs a privilege, and
   a person runs it.

   The start-up unit sounds the `booted` pattern, after it asserts the hold. The sound tells
   an operator that the hold is on, and that a soft power button can be released. The Actor
   cannot give this signal, because the operator needs it seconds before Aiko Services
   starts. The unit and the hook both render their durations from the one table of patterns.
   Each sound command of the unit can fail without effect, because the duty of the unit is
   the hold. A buzzer that does not sound must never report the hold as a failure.

10. **A battery percentage is earned by measurement.** Until a discharge curve is measured on
    the hardware, the Implementation reports voltage, current, power and the battery
    temperature, and the policy uses a voltage that the battery pack must not go below. A percentage
    and an estimated time are published only after a measured curve exists.

11. **A quiesce mode before the power ends, and a read-only remount at the floor.** The
    battery is finite, so a host that keeps the power on is only delaying the end. When the
    Actor knows that the power will end, it publishes `mode` as `quiesce` with the reason,
    synchronizes the file systems, and runs a declared hook. Applications observe the mode
    and stop writing. The mode is reached by an orderly shutdown, by a battery that nears
    its floor, and by a shutdown hook that is reported missing.

    At the floor voltage the Actor goes one step further and remounts the file systems
    read-only, before it starts the shutdown. **The trigger is the floor that the policy
    uses, which is the lowest voltage that this design operates at. The cell damage limit is
    never a trigger**, because this design never reaches it. A test asserts that no code path
    reads the damage limit as a threshold.

    The remount can fail, because a file system refuses to go read-only while a process holds
    a file open for writing. A failure is reported and counted, and the shutdown continues. A
    failed remount must never stop a shutdown: a host that is still writing is better off
    halted than left running on the last of the charge. After the remount the Actor cannot
    write its own log, so the log is closed first and the shared state carries what matters.

    The alternative to a hold that fails safe is a release that the Actor makes, and that is
    worse: it cuts the power of a running host. This decision keeps the safe direction and
    removes its cost.

12. **The privileged operations are granted explicitly, and rendered.** An Actor runs
    unprivileged, so the power-off and the remount of decision 11 both need a grant from the
    operating system. The grant names the exact commands and nothing else, with absolute
    paths, no wildcard, and the account rendered rather than written into the code. `render`
    prints it before `install` writes it, under decision 9.

    `install` validates the grant before it writes it, and it writes atomically with the mode
    set before the rename. A grant file that is malformed, or that is half written, can deny
    the administrator the privilege to repair it. On a host with no console that is an
    unrecoverable state, so validation is part of the decision and not an implementation
    detail.

    A `verify` operation reports whether the grant and the shutdown hook are in place, and it
    reports this without using either. The Actor publishes the report. A host that cannot
    power itself off has a battery policy that is advisory, whatever its thresholds say, and
    an operator must be able to see that.

    The mechanism behind the grant is deliberately not fixed here. A privileged executable
    with the set-user-id bit, and a privileged unit of the operating system that the Actor
    asks for, are both candidates to weigh later. The second needs no such bit and no
    elevation helper, and it agrees with ADR-026, where the operating system already starts
    what Aiko Services needs. What this decision fixes is the shape: two named operations, an
    explicit grant, validation before installation, and a report.

13. **Up-time is requested by Lease, and no application is named.** A host may be needed by
    zero, one or many clients, and each one knows its own business. So the policy asks one
    question of everybody: does anything still need this host? A client answers by holding a
    Lease, with `(request_powered_up RESPONSE_TOPIC SECONDS REASON)`, keyed by the client's own
    topic and extended before it expires. Zero seconds releases it. This is the shape that
    `ECProducer` already uses for shared state, so it adds no mechanism.

    The policy counts live requests, and it no longer asks any Actor what work it has left.
    Thus the "unknown" case disappears. A client that cannot be reached cannot hold a Lease,
    and a Lease that nothing extends expires. So "nobody answered" and "nobody needs me"
    become one measurable thing.

    Two limits are part of this decision, and not an implementation detail: the longest single
    request that is granted, and how many may be held at once. A request can only ask a host
    to stay up, a refusal is always available, and those limits bound what a client in a loop
    can do. Therefore the request belongs in the safe posture of decision 7. A Lease asks; it
    never commands, and it never outlives the battery floor, the battery pack temperature gate
    or the deadline on an undocked hold.

    **A deployment may set its own deadline, and the deadline beats every claim.** Two
    thresholds set the deadline on an undocked hold, and the shorter one applies. The backstop
    says that no host runs on its battery pack for ever, and it is not meant to be reached. A
    grace period is a deployment's own rule: when the supply goes, and does not come back, the
    host stops after that long whatever work is claimed. A supply that comes back cancels it,
    because the count is how long the host has been undocked, and a dock makes that zero.

    The grace period is off by default, and then a host behaves as though the threshold did
    not exist. One rule reads both thresholds, so there is one row in the policy and not two
    that can disagree, and the decision names which threshold fired. The two mean different
    things, so a log that names only "a deadline" would explain nothing.

    A deadline that ends a hold is a graceful stop, and not a cut: it reaches the quiesce mode
    of decision 11 first, so the writers are told and the file systems are flushed.

    The refusal vocabulary is the one that the framework's own Lease already proposes, so one
    spelling serves both.

    **A Lease has two conditions, and both must hold.** The lease time is the period for
    which it is valid, and a client extends it. A constraint is a quantity of a finite
    resource, in whatever unit measures that resource, and the host must still be able to meet
    it. A Lease whose time is current but whose constraint cannot be met is not usable, so it
    stops counting as a reason to keep the host up, and its holder is told.

    A battery pack is finite in energy, not in seconds, which is why the second condition
    exists. The unit is named rather than assumed, so a later resource needs a name and a
    measurement and nothing else. Watt-hours of the battery pack is the first one.

    **A constraint in a unit the host cannot measure is refused, and never granted.** Granting
    what cannot be checked is worse than refusing it, because the client would then plan on a
    promise that nothing can keep. One finite resource is also shared, so the answer is for
    the whole of it: two clients that each ask for 20 Wh of 30 Wh are each satisfiable and
    together are not. The rule is first granted, first served, which is arbitrary in the way
    that any fair rule is, and at least one that a person can predict.

    **The Lease is the framework's Lease.** `PoweredUpLease` extends it, as `ECLease` does, so
    the expiry runs at the time that was agreed and not at the next convenient moment. Prompt
    action at the agreed timeout is a large part of what a Lease is for: the last Lease to
    expire is the event that lets a host stop, and a host that waited for its next reading
    would hold a battery pack up for nobody. A client holds a Lease of its own as well, which
    extends itself, so both ends of the agreement are a Lease and both act on time.

    A client helper lives in the framework core, and not beside the Actor that answers it. Any
    Service may need its host to stay up, and the core must not depend on the Actor tier. The
    protocol that the power manager registers is named there as the default of a parameter,
    which is the only thing the core needs to know about it.

14. **A sound tells an operator one thing, and the power manager owns which sound.** A host
    in service can have no screen, and a person near it must know four things: the host holds
    its own power, a press of the button was long enough, an application does its work, and
    the host is going down. One pattern says each.

    A buzzer has one pitch, so a pattern is told apart by its rhythm and by its length. Two
    rules come from that. A sound an operator waits for ends on a long note, which is the part
    that carries across a room. A sound that reports a loss is fast and repeated. The patterns
    are a table of durations, so a new sound is a table entry and a test compares a list.

    **Two of the four are played without any Actor.** The hold is asserted before Aiko Services
    starts, and released after the file systems are gone, and an operator needs a sound at both
    of those moments. So the start-up unit and the shutdown hook of decision 9 render the same
    table as commands for the platform's pin utility. The table stays the one source.

    **The sound that answers the button is prompt, and the Actor is not what makes it.** The
    stop of the start-up unit sounds the shutdown pattern while the host is still up, which is
    seconds after the press rather than after the file systems are unmounted. It therefore
    answers every cause of a shutdown, and not the button alone. The hook sounds the same
    pattern again at the end, where it means that the power goes now. The stop releases
    nothing: only the hook releases the hold, and a release at the stop would cut the power of
    a host that is restarting.

    **An application reports that it works, and never asks for a sound.** Only the application
    knows what working means for it, and this Actor cannot know it without naming the
    application, which decision 13 forbids. So the direction is the same as the Lease:
    `(report_working RESPONSE_TOPIC DETAIL)`, keyed by the reporter's own topic. This Actor
    chooses the pattern and bounds the rate: one sound for each reporter, then a dwell, and a
    cap on the reporters kept. Nothing is published in answer, because the outcome is the
    shared state.

    That surface is in the safe posture of decision 7, and `signal` stays out of it. The
    difference is real and not a matter of degree: a reporter states a fact and this Actor
    decides what it costs a person, whereas `signal` is control of a device that reaches a
    person. The two limits are part of this decision, as decision 13's limits are, and not
    found later.

    A client helper lives in the framework core for the reason decision 13 gives. Its
    discovery is today a second copy of the Lease client's, which a third client should make
    into one.

15. **A person is not a threshold, so the button acts whatever the posture.** The advisory
    posture of decision 7 exists because the voltage and temperature thresholds come from a
    data sheet, and not from the battery pack that is fitted. A person who holds the button for
    three seconds is not a measurement, and no calibration makes their request more or less
    true. A power button that does nothing is a fault to the operator who pressed it.

    So the two are separate. Advisory still means that no measured reason acts. A held button
    stops the host, and one switch turns off even that, for a host where nothing may stop the
    operating system. Whether a press acts is published in the shared state, so that an
    operator reads it rather than infers it.

    This decision is numbered last and read first. In the order of the rows that decision 8
    gives, the button comes before every other reason, and this is why: the other rows need a
    measurement to be right, and this one needs only a person.

    A press is answered at once, and not after the grace that a shutdown at the voltage floor
    waits out. The change of mode has already told the writers and flushed the file systems,
    and the power-off unmounts in an orderly way by itself. Waiting would cost the operator a
    whole sample period, which is a minute on a host that samples once a minute.

    The mock Implementation records the power-off rather than running it. A test that reaches
    the acting path would otherwise stop the machine that runs the test suite, which this
    change discovered on a host with password-less privilege.

## Consequences

**Good.**

- Power becomes observable in the way that everything else is: shared state that the
  Dashboard, a display and any other client read. There is no new management plane (P6).
- The policy is testable with no Device, no battery and no board, because the mock is the
  default and `decide()` is pure.
- A developer runs the same Actor on a laptop, which is where most of the code is written.
- The hold survives every software failure that is not a release. That is the correct
  direction for a host that has custody of data.
- The restart rule removes a class of field failure in which a host goes away and does not
  come back.
- The quiesce mode gives applications a warning that no operating system gives them.

**Costs, which this record accepts.**

- The hold depends on a platform utility through a subprocess, which is a dependency that the
  project otherwise avoids. Decision 5 states why. The Interface hides it, so a second
  Implementation is a small change.
- The shutdown hook lives outside Aiko Services, in the operating system. ADR-026 accepted
  that shape for the daemon already, and decision 9 keeps the same discipline.
- A failed hook leaves a halted host on its battery until the battery is empty. Decision 11
  makes that outcome safe for the data. It still costs a charge, and the Actor reports it.
- A client that needs the host to stay up must extend a Lease. That is more work for it than
  publishing a queue depth and letting the policy read it. It is the cost of a policy that
  knows what no application is, and decision 13 accepts it.
- One Interface with property tokens means that a client reads the properties before it trusts
  a method. Four aspect Interfaces would have told it through discovery. Decision 2 accepts
  this, because the policy is then one place and not four.
- Four Implementations of one Actor-level Interface share their Actor behavior through a
  mixin. A reader must look in two files to see one Implementation whole.
- Two privileged operations need a grant that an administrator installs (decision 12). Thus a
  deployment has one more file to review. The alternative is an Actor that runs with a
  privilege it does not need for anything else it does.

## Evidence trail

- **Principles.** P2 (Actors share nothing: the power manager never draws on a display, and a
  display never reads a sensor). P5 (discovery over configuration: the transfer queue is found
  by `ServiceFilter`, and not by a path). P6 (everything is a Service). P7 and ADR-022
  (composition, and the three exemptions). P9 (edge frugality: two small register drivers,
  rather than a package tree). P12 and ADR-023 (deny by default, and the explicit unsafe
  posture of decision 6 of that record). P11 as a candidate (the device callbacks post to the
  mailbox, and never touch Actor state).
- **Precedents.** ADR-026 for one Interface with an Implementation for each platform, and for
  `render` before `install`. ADR-025 for an Actor package with its own protocol, and for
  aspects advertised as tags. `ProcessManagerImpl` for the safe and unsafe postures, and for
  an Interface that extends `Actor`. The WhisPlay button for the pure classification of a long
  press. `NullOutputImpl` for a backend that lacks a method, and `_Emulated` for a shared
  mixin.
- **Measurements.** The hardware survey of a Device on 2026-11-05. Both power meters answer,
  and the battery temperature sensor answers. The hold pin is an input with a pull-up, which
  is not an asserted hold. The project lead confirmed by hand that the pin controls the relay
  in both directions.
