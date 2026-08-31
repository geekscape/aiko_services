---
title: Aiko Services — Getting Started (the recipe)
description: A 15-minute copy-paste recipe from nothing to a running pipeline plus an AI-assistant setup — no programming experience needed
type: guide
audience: [application-developers]
status: operational
ste: adapted
last_updated: 2026-08-31
---

# Aiko Services — Getting Started (the recipe)

Build something real with an AI coding assistant, on a framework that
keeps the code good even when you are new. Follow the steps in order.
Each step tells you what you should see. Total time: about 15 minutes.

You need: a computer (Windows, Mac or Linux), its terminal app
(Windows: **PowerShell** · Mac/Linux: **Terminal**), and an AI coding
assistant (like Claude Code). You do **not** need to be a programmer.

---

## 1. Check you have Python

Open your terminal. Type this and press Enter:

**Mac / Linux:**

```bash
python3 --version
```

**Windows (PowerShell):**

```powershell
python --version
```

**You should see:** something like `Python 3.11.6` (any 3.9 or higher is
fine). If you get "command not found" / "not recognized", install Python
from python.org first — on Windows, tick **"Add Python to PATH"** in the
installer — then come back.

## 2. Make a workspace

**Mac / Linux:**

```bash
mkdir my_app
cd my_app
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell):**

```powershell
mkdir my_app
cd my_app
python -m venv venv
venv\Scripts\Activate.ps1
```

**You should see:** `(venv)` appear at the start of your prompt. That
means you are in a clean workspace. (Any time you open a new terminal,
go back into `my_app` and run the activate line again.)

## 3. Install the framework

```bash
pip install aiko_services
```

**You should see:** lines ending with `Successfully installed ...`.

## 4. Get the examples

```bash
git clone https://github.com/geekscape/aiko_services.git framework
```

**You should see:** a new `framework` folder appear. It holds working
examples your AI assistant will learn from.

## 5. Run your first pipeline (the "hello world")

```bash
aiko_pipeline create framework/src/aiko_services/examples/pipeline/pipeline_example.json -s 1 -p limit 10 -p rate 1
```

**You should see:** lines printing as data flows through a small
processing pipeline, then it stops. That is the framework working, all in
one window, nothing else needed. 🎉

If it worked — you are ready to build. If not, see Troubleshooting below.

## 6. Add the rulebook file

This is the important one. Create a file called `Agents.md` in your
`my_app` folder, containing exactly this (copy-paste, then change the
first line to describe YOUR app):

```markdown
# MyApp: Agent instructions

MyApp is built on the Aiko Services framework
(github.com/geekscape/aiko_services) and follows its Design
Principles: constitution/p_00_DesignPrinciples.md in that repository.

Rules for every coding session:
- Read the Design Principles before designing anything. When you make
  a design decision, say which principle (P-number) guided it.
- Prefer building a Pipeline of PipelineElements. Reuse existing
  elements from framework/src/aiko_services/elements/ before writing
  new ones. Learn from framework/src/aiko_services/examples/pipeline/.
- Never make a method return a value across the network. Never use
  async/await with the framework. Never hard-code addresses or topics.
- Always write "Aiko Services" in full. Name ReadMe files "ReadMe.md".
```

Then link it for Claude (one command):

**Mac / Linux:**

```bash
ln -s Agents.md CLAUDE.md
```

**Windows (PowerShell):**

```powershell
cmd /c mklink CLAUDE.md Agents.md
```

(If Windows refuses the link, just copy instead — `copy Agents.md
CLAUDE.md` — and remember: always edit `Agents.md`, then re-copy.)

**Why this file matters (one sentence):** your AI assistant reads it
automatically at the start of every session, so it follows the
framework's rules without you having to know them.

## 7. Start your AI assistant and paste this prompt

> Read Agents.md, then the Aiko Services Design Principles it points to.
> I want to build: **[describe your idea in one or two sentences]**.
> Propose a simple Pipeline design first. Which existing elements can
> we reuse? What (if anything) must we write? Tell me which
> P-numbers guided the design. Keep it as simple as possible.

Then just talk to it. Ask questions. Ask it to run things and show you.

## 8. Your first change (a good warm-up)

Ask your assistant:

> Copy the example pipeline into our project and change it to process
> 20 items instead of 10. Run it and show me the output.

**You should see:** your own copy of the pipeline, doing your bidding.
From here, it is your idea, one small step at a time.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `command not found` / `not recognized`: `aiko_pipeline` | Re-run the activate line from step 2 — you are not in the workspace |
| `python3` / `python` not found | Install Python from python.org (Windows: tick "Add Python to PATH") |
| `git` not found | Windows: install from git-scm.com. Mac: run `xcode-select --install`. Linux: `sudo apt install git` |
| Windows: "running scripts is disabled" when activating | Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`, answer Y, then activate again |
| Windows: `mklink` says access denied | Use the copy fallback in step 6 |
| Something else | Paste the exact error into your AI assistant and ask |

## When you are ready for more

- [**Tutorial: First project**](tutorials/first_project.md) explains
  everything this recipe skipped — the two ways to start (Pipeline or
  Actor), and what the Design Principles actually say. More tutorials:
  [the tutorials index](tutorials/ReadMe.md).
- When your app should talk to other apps across machines: ask your
  assistant about "running with a broker, the Registrar and the
  Dashboard". Your pipeline will not need rewriting — that is a promise the
  framework's rules keep for you.
