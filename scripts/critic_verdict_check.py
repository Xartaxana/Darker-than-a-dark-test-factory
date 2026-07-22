"""Fail-closed checker for critic verdict JSON blocks (task os-port-0722,
port of D:\\Improving_AI\\Operating-System-for-LLMs tools/critic_verdict_check.py).

Extracts the LAST fenced ```json ... ``` block from a critic's final-message
text and validates it against the shape declared in
schemas/critic-verdict.schema.json. Rules are hardcoded here (not a generic
JSON-Schema validator by design); scripts/tests/test_critic_verdict_check.py
carries an anti-drift check comparing this file's behavior against the
schema.

ADAPTATION over the OS original (Lead decision, task os-port-0722 spec, part
(в)): the 'verdict' enum is Russian, verbatim from .claude/agents/critic.md
rule 6 -- ПРИНЯТЬ / ДОРАБОТАТЬ / ОТКЛОНИТЬ -- instead of the OS repo's
English fit/fit_with_fixes/blocker. No English<->Russian mapping is kept
anywhere: a single dictionary, so the agent prompt's wording and the
machine schema cannot drift apart.

Usage:
    python scripts/critic_verdict_check.py <path-to-verdict-text>
    python scripts/critic_verdict_check.py -        (reads stdin)

Exit codes:
    0  valid verdict -> stdout: "VERDICT OK: <verdict>, blockers: N, fixes: M"
    1  no block / broken JSON / not an object / schema violation -> stderr:
       ASCII diagnostic lines, one per violation, each naming the concrete
       field/rule that failed.

All diagnostic text and the success line are ASCII-only by construction:
diagnostics never interpolate raw field VALUES from the (possibly
non-ASCII) input, only field names, indices and fixed expected-shape text.
The verdict word itself IS Cyrillic by design (ПРИНЯТЬ/ДОРАБОТАТЬ/
ОТКЛОНИТЬ) -- printing it on the success line is therefore made resilient
to a narrow console codepage the same way scripts/log_append.py's own
stdout is (see main(): stdout is reconfigured to UTF-8 with errors=
"replace" before any output, so a UnicodeEncodeError on cp1251/cp866
becomes a replacement character instead of a crash, never a false exit 1).

Two sharp edges of the fence-extraction regex, both intentional trade-offs
of the "no generic parser" design:
  - The fence opener is matched case-sensitively as a literal lowercase
    ```json. ```JSON, ```Json or a bare ``` opener are NOT recognized as
    a verdict block.
  - The block body is matched non-greedily up to the first ``` that
    follows the opener. A verdict field VALUE that itself contains a
    literal ``` sequence truncates the captured body there: the JSON
    typically fails to parse (or parses into something that no longer
    satisfies the schema), so an otherwise-valid verdict is rejected
    fail-closed rather than silently misread.
"""

import json
import re
import sys

VERDICT_ENUM = ("ПРИНЯТЬ", "ДОРАБОТАТЬ", "ОТКЛОНИТЬ")

_FENCE_RE = re.compile(r"```json[ \t]*\r?\n(.*?)```", re.DOTALL)


def extract_last_json_block(text):
    """Return the text of the LAST closed ```json ... ``` fence, or None."""
    matches = list(_FENCE_RE.finditer(text))
    if not matches:
        return None
    return matches[-1].group(1)


def _is_str_list(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def validate_verdict(obj):
    """Return a list of ASCII violation strings; empty list means valid."""
    errors = []

    if not isinstance(obj, dict):
        errors.append(
            "JSON root is not an object (type: %s)" % type(obj).__name__
        )
        return errors

    required_top = ("verdict", "blockers", "class_completeness", "trail")
    for field in required_top:
        if field not in obj:
            errors.append("missing required field: %s" % field)

    # verdict
    verdict = obj.get("verdict")
    verdict_valid = False
    if "verdict" in obj:
        if not isinstance(verdict, str) or verdict not in VERDICT_ENUM:
            errors.append(
                "field 'verdict' invalid: expected one of "
                "PRINYAT/DORABOTAT/OTKLONIT (Cyrillic, exact match; see schema)"
            )
        else:
            verdict_valid = True

    # blockers
    blockers = obj.get("blockers")
    blockers_valid = False
    if "blockers" in obj:
        if not _is_str_list(blockers):
            errors.append("field 'blockers' must be an array of strings")
        else:
            blockers_valid = True

    if verdict_valid and blockers_valid:
        if verdict == "ПРИНЯТЬ" and len(blockers) != 0:
            errors.append(
                "field 'blockers' must be empty when verdict is PRINYAT"
            )
        if verdict == "ОТКЛОНИТЬ" and len(blockers) == 0:
            errors.append(
                "field 'blockers' must be non-empty when verdict is OTKLONIT"
            )

    # class_completeness
    if "class_completeness" in obj:
        if not isinstance(obj.get("class_completeness"), str):
            errors.append("field 'class_completeness' must be a string")

    # trail
    if "trail" in obj:
        trail = obj.get("trail")
        if not isinstance(trail, dict):
            errors.append("field 'trail' must be an object")
        else:
            if "read" not in trail:
                errors.append("missing required field: trail.read")
            elif not _is_str_list(trail.get("read")):
                errors.append("field 'trail.read' must be an array of strings")

            if "reruns" not in trail:
                errors.append("missing required field: trail.reruns")
            else:
                reruns = trail.get("reruns")
                if not isinstance(reruns, list):
                    errors.append("field 'trail.reruns' must be an array")
                else:
                    for idx, item in enumerate(reruns):
                        if not isinstance(item, dict):
                            errors.append(
                                "field 'trail.reruns[%d]' must be an object" % idx
                            )
                            continue
                        if "command" not in item or not isinstance(
                            item.get("command"), str
                        ):
                            errors.append(
                                "field 'trail.reruns[%d]' missing required string field: command"
                                % idx
                            )
                        if "result" not in item or not isinstance(
                            item.get("result"), str
                        ):
                            errors.append(
                                "field 'trail.reruns[%d]' missing required string field: result"
                                % idx
                            )

    # fixes (conditionally required)
    if verdict_valid and verdict == "ДОРАБОТАТЬ":
        fixes = obj.get("fixes")
        if "fixes" not in obj:
            errors.append(
                "missing required field: fixes (required when verdict is DORABOTAT)"
            )
        elif not _is_str_list(fixes):
            errors.append("field 'fixes' must be an array of strings")
        elif len(fixes) == 0:
            errors.append("field 'fixes' must be non-empty when verdict is DORABOTAT")
    elif "fixes" in obj and obj.get("fixes") is not None:
        if not _is_str_list(obj.get("fixes")):
            errors.append("field 'fixes' must be an array of strings")

    return errors


def check_text(text):
    """Run the full pipeline on raw text. Returns (ok, errors, obj_or_None)."""
    block = extract_last_json_block(text)
    if block is None:
        return False, ["no fenced ```json block found in input"], None

    try:
        obj = json.loads(block)
    except json.JSONDecodeError as exc:
        return False, ["invalid JSON in fenced block: %s" % str(exc)], None

    errors = validate_verdict(obj)
    if errors:
        return False, errors, obj
    return True, [], obj


def main(argv):
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    if len(argv) != 2:
        sys.stderr.write("usage: critic_verdict_check.py <path-or-->\n")
        return 1

    source = argv[1]
    if source == "-":
        try:
            raw = sys.stdin.buffer.read()
        except AttributeError:
            raw = sys.stdin.read().encode("utf-8", "surrogateescape")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            sys.stderr.write("INVALID VERDICT: input is not valid UTF-8\n")
            return 1
    else:
        try:
            with open(source, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            sys.stderr.write("cannot read input file: %s\n" % str(exc))
            return 1
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            sys.stderr.write("INVALID VERDICT: input is not valid UTF-8\n")
            return 1

    ok, errors, obj = check_text(text)
    if not ok:
        sys.stderr.write("INVALID VERDICT:\n")
        for err in errors:
            sys.stderr.write("  - %s\n" % err)
        return 1

    blockers = obj.get("blockers") or []
    fixes = obj.get("fixes") or []
    sys.stdout.write(
        "VERDICT OK: %s, blockers: %d, fixes: %d\n"
        % (obj.get("verdict"), len(blockers), len(fixes))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
