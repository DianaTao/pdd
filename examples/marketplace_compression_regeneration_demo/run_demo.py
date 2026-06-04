#!/usr/bin/env python3
"""Marketplace few-shot compression regeneration benchmark (#876).

Runs ``pdd generate`` twice (uncompressed vs ``--compress``) through the normal
cloud generation branch. Fixture marketplace records mirror cloud ``examplesUsed``
shape; few-shot injection text is built from per-example ``.prompt``/``.py``
files. Compressed few-shot code uses ``apply_compressed_include_with_fallback``
(the same #876 path as CLI compression).

CI uses representative HTTP stubs. Pass ``--live`` (or set
``PDD_MARKETPLACE_DEMO_LIVE=1``) for a real PDD Cloud + model run with
marketplace few-shot validation (seeds fixture examples, pins catalog slugs,
requires ``source: marketplace`` unless ``--allow-non-marketplace``).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

from click.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pdd.commands.generate import generate  # noqa: E402
from pdd.content_selector import apply_compressed_include_with_fallback  # noqa: E402
from pdd.grounding_provenance import selected_examples_from_cloud  # noqa: E402
from pdd.preprocess import preprocess  # noqa: E402

DEMO_DIR = Path(__file__).resolve().parent
PROMPT = DEMO_DIR / "prompts" / "ticket_classifier_python.prompt"
MARKETPLACE_EXAMPLES = DEMO_DIR / "fixtures" / "marketplace_examples.json"
MARKETPLACE_FIXTURES = DEMO_DIR / "fixtures" / "marketplace"
MOLD_PY = DEMO_DIR / "fixtures" / "ticket_classifier_mold.py"
GENERATED_DIR = DEMO_DIR / "generated"
# Must live under prompts/ with *_python.prompt so PDD detects language=python.
LIVE_PROMPT = DEMO_DIR / "prompts" / "ticket_classifier_live_python.prompt"
REPORT_PATH = GENERATED_DIR / "marketplace_compression_report.json"

_CREATOR_NOTES_RE = re.compile(
    r"\n\nCreator notes \(provenance only\):.*?(?=\n\n|\Z)",
    re.DOTALL,
)

_PLACEHOLDER_PIN_MARKERS = (
    "your/cloud",
    "other/slug",
    "slug/from",
    "example.com",
)


def _estimated_tokens(text: str) -> int:
    return -(-len(text) // 4)


def _load_marketplace_catalog() -> list[dict[str, Any]]:
    return json.loads(MARKETPLACE_EXAMPLES.read_text(encoding="utf-8"))


def _is_placeholder_pin(module: str) -> bool:
    lowered = module.lower()
    return any(marker in lowered for marker in _PLACEHOLDER_PIN_MARKERS)


def _filter_placeholder_pins(modules: list[str]) -> list[str]:
    return [module for module in modules if module and not _is_placeholder_pin(module)]


def _pin_modules_from_env() -> list[str]:
    env = os.environ.get("PDD_MARKETPLACE_DEMO_PIN_MODULES", "").strip()
    if not env:
        return []
    return _filter_placeholder_pins(
        [part.strip() for part in env.split(",") if part.strip()]
    )


def _catalog_pin_modules(catalog: list[dict[str, Any]]) -> list[str]:
    return [str(row["module"]) for row in catalog if row.get("module")]


def _evidence_basename_for_prompt(prompt_path: Path) -> str:
    name = prompt_path.name
    if name.endswith("_python.prompt"):
        return name[: -len("_python.prompt")]
    if name.endswith(".prompt"):
        return name.removesuffix(".prompt")
    return prompt_path.stem


def _fixture_marketplace_few_shot_metrics(
    catalog: list[dict[str, Any]],
) -> dict[str, int]:
    """Sizes for catalog marketplace few-shot blocks (#876 compress path)."""
    uncompressed = _build_marketplace_few_shot_context(catalog, compress=False)
    compressed = _build_marketplace_few_shot_context(catalog, compress=True)
    return {
        "uncompressed_chars": len(uncompressed),
        "compressed_chars": len(compressed),
        "reduction_chars": len(uncompressed) - len(compressed),
    }


def _submit_marketplace_fixture(
    row: dict[str, Any],
    *,
    jwt_token: str,
) -> dict[str, Any] | None:
    """Upload a catalog fixture to PDD Cloud so pins can resolve in the tenant."""
    import requests

    from pdd.core.cloud import CloudConfig, get_cloud_request_timeout

    prompt_path = DEMO_DIR / row["promptFile"]
    code_path = DEMO_DIR / row["codeFile"]
    prompt_content = prompt_path.read_text(encoding="utf-8")
    processed_prompt = preprocess(
        prompt_content,
        recursive=False,
        double_curly_brackets=True,
    )
    code_content = code_path.read_text(encoding="utf-8")
    payload: dict[str, Any] = {
        "command": "benchmark",
        "searchInput": prompt_content,
        "input": {
            "prompts": [{"content": processed_prompt, "filename": prompt_path.name}],
            "code": [{"content": code_content, "filename": code_path.name}],
        },
        "output": {
            "code": [{"content": code_content, "filename": code_path.name}],
        },
        "metadata": {
            "title": row["title"],
            "description": "PDD #876 marketplace compression regeneration benchmark fixture",
            "language": "python",
            "framework": "",
            "tags": ["marketplace", "pdd-benchmark-876", "few-shot"],
            "isPublic": True,
            "price": 0.0,
        },
    }
    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}
    response = requests.post(
        CloudConfig.get_endpoint_url("submitExample"),
        json=payload,
        headers=headers,
        timeout=get_cloud_request_timeout(),
    )
    if response.status_code != 200:
        return None
    try:
        body = response.json()
    except json.JSONDecodeError:
        return None
    return body if isinstance(body, dict) else None


def _module_slug_from_submit_response(body: dict[str, Any]) -> str | None:
    for key in ("module", "slug", "moduleSlug", "module_slug"):
        value = body.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    for nested_key in ("example", "result", "data"):
        nested = body.get(nested_key)
        if isinstance(nested, dict):
            found = _module_slug_from_submit_response(nested)
            if found:
                return found
    return None


def _seed_marketplace_fixtures(
    catalog: list[dict[str, Any]],
    *,
    jwt_token: str,
    verbose: bool,
) -> list[str]:
    """Submit catalog fixtures; return any cloud-assigned module slugs."""
    submitted: list[str] = []
    for row in catalog:
        body = _submit_marketplace_fixture(row, jwt_token=jwt_token)
        if body is None:
            if verbose:
                print(
                    f"Warning: could not submit fixture {row.get('module')} "
                    "(submitExample failed or returned non-JSON)",
                    file=sys.stderr,
                )
            continue
        slug = _module_slug_from_submit_response(body)
        if slug:
            submitted.append(slug)
        if verbose:
            print(
                f"Seeded fixture {row.get('module')} to cloud"
                + (f" -> {slug}" if slug else ""),
                file=sys.stderr,
            )
    return submitted


def _resolve_live_pin_modules(
    catalog: list[dict[str, Any]],
    *,
    seed: bool,
    verbose: bool,
) -> tuple[list[str], list[str]]:
    """Return (pin_modules, seeded_cloud_slugs) for a strict marketplace live run."""
    from pdd.core.cloud import CloudConfig

    env_pins = _pin_modules_from_env()
    catalog_pins = _catalog_pin_modules(catalog)
    seeded: list[str] = []
    if seed and os.environ.get("PDD_MARKETPLACE_DEMO_NO_SEED", "").lower() not in (
        "1",
        "true",
        "yes",
    ):
        jwt_token = CloudConfig.get_jwt_token(verbose=False)
        if jwt_token:
            seeded = _seed_marketplace_fixtures(catalog, jwt_token=jwt_token, verbose=verbose)
    if env_pins:
        return env_pins, seeded
    combined = list(dict.fromkeys([*catalog_pins, *seeded]))
    return combined, seeded


def _pin_modules_for_live(
    catalog: list[dict[str, Any]],
    *,
    seed: bool,
    verbose: bool,
) -> tuple[list[str], list[str]]:
    return _resolve_live_pin_modules(catalog, seed=seed, verbose=verbose)


def _prompt_for_run(*, live: bool, pin_modules: list[str]) -> Path:
    if not live:
        return PROMPT
    pin_block = "\n".join(f"<pin>{module}</pin>" for module in pin_modules)
    LIVE_PROMPT.write_text(
        f"{pin_block}\n\n{PROMPT.read_text(encoding='utf-8')}",
        encoding="utf-8",
    )
    return LIVE_PROMPT


def _ensure_cloud_auth() -> None:
    """Fail fast with a clear message when JWT is missing or expired."""
    from pdd.core.cloud import CloudConfig

    token = CloudConfig.get_jwt_token(verbose=False)
    if not token:
        raise RuntimeError(
            "PDD Cloud auth failed. Run: pdd auth logout && pdd auth login"
        )


def _selected_have_marketplace_source(
    selected: list[dict[str, Any]],
) -> bool:
    return any(ex.get("source") == "marketplace" for ex in selected)


def _live_marketplace_verified(
    selected: list[dict[str, Any]],
    *,
    catalog: list[dict[str, Any]],
    pin_modules: list[str],
) -> tuple[bool, str]:
    """Whether live cloud used catalog/seeded marketplace few-shot (by source or pin match)."""
    if _selected_have_marketplace_source(selected):
        return True, "cloud tagged examples source=marketplace"
    catalog_modules = {str(row["module"]) for row in catalog if row.get("module")}
    selected_modules = {str(ex.get("module")) for ex in selected if ex.get("module")}
    if catalog_modules & selected_modules:
        return True, "cloud selected catalog marketplace module slugs"
    if pin_modules and selected_modules & set(pin_modules):
        return True, "cloud honored <pin> for seeded/catalog marketplace fixtures"
    return False, "no marketplace source and pins did not resolve"


def _validate_live_grounding(
    evidence: dict[str, Any],
    *,
    catalog: list[dict[str, Any]],
    pin_modules: list[str],
    allow_non_marketplace: bool,
    selected_examples: list[dict[str, Any]] | None = None,
) -> str | None:
    """Validate real cloud grounding; return warning text or None."""
    grounding = (evidence.get("generation") or {}).get("grounding") or {}
    if grounding.get("mode") != "cloud":
        raise RuntimeError(
            f"live run: expected cloud grounding, got {grounding.get('mode')!r}. "
            "Cloud may have fallen back to local (check auth/API keys in output)."
        )
    selected = selected_examples or grounding.get("selected_examples") or []
    if not selected:
        raise RuntimeError(
            "live run: cloud returned no examplesUsed. "
            "Try PDD_MARKETPLACE_DEMO_PIN_MODULES with modules that exist in your cloud library."
        )

    verified, _reason = _live_marketplace_verified(
        selected,
        catalog=catalog,
        pin_modules=pin_modules,
    )
    if verified:
        return None

    if allow_non_marketplace:
        return (
            "Cloud examples were not tagged source=marketplace "
            f"(selected={[ex.get('module') for ex in selected]}). "
            "Fixture marketplace few-shot compression is still reported in "
            "fixture_marketplace_few_shot; use default run_demo.py (no --live) for "
            "representative marketplace regeneration proof."
        )

    raise RuntimeError(
        "Live run did not use marketplace few-shot examples "
        f"(selected={[ex.get('module') for ex in selected]}, "
        f"sources={[ex.get('source') for ex in selected]}). "
        "Set PDD_MARKETPLACE_DEMO_PIN_MODULES to real marketplace module slugs, "
        "or run without --live for the CI representative marketplace benchmark: "
        "python examples/marketplace_compression_regeneration_demo/run_demo.py"
    )


def _cloud_examples_used(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shape expected by ``code_generator_main`` / cloud ``examplesUsed``."""
    cloud_rows: list[dict[str, Any]] = []
    for row in catalog:
        cloud_rows.append(
            {
                "id": row["id"],
                "module": row.get("module") or row.get("slug"),
                "title": row["title"],
                "source": row["source"],
                "similarity": row["similarity"],
                "promptSha256": row.get("promptSha256") or row.get("prompt_sha256"),
                "codeSha256": row.get("codeSha256") or row.get("code_sha256"),
            }
        )
    return cloud_rows


def _compress_marketplace_prompt_text(text: str) -> str:
    """Drop provenance-only narrative; keep few-shot Input/Output pairs."""
    return _CREATOR_NOTES_RE.sub("", text).strip()


def _build_marketplace_few_shot_context(
    catalog: list[dict[str, Any]],
    *,
    compress: bool,
) -> str:
    """Synthesize cloud-injected marketplace few-shot block from fixture files."""
    blocks: list[str] = []
    for row in catalog:
        prompt_path = DEMO_DIR / row["promptFile"]
        code_path = DEMO_DIR / row["codeFile"]
        prompt_text = prompt_path.read_text(encoding="utf-8")
        code_text = code_path.read_text(encoding="utf-8")
        if compress:
            prompt_text = _compress_marketplace_prompt_text(prompt_text)
            code_text = apply_compressed_include_with_fallback(
                code_text,
                file_path=str(code_path),
            )
        blocks.append(
            f"## {row['title']} ({row['module']})\n"
            f"{prompt_text.strip()}\n\n"
            f"```python\n{code_text.strip()}\n```"
        )
    return "\n\n".join(blocks)


def _generated_code_from_mold() -> str:
    """Target module body aligned with the local mold + marketplace contracts."""
    return MOLD_PY.read_text(encoding="utf-8")


@contextmanager
def _compression_env(enabled: bool):
    previous_mode = os.environ.get("PDD_CONTEXT_COMPRESSION")
    previous_examples = os.environ.get("PDD_COMPRESS_EXAMPLES")
    try:
        if enabled:
            os.environ["PDD_CONTEXT_COMPRESSION"] = "examples,contracts"
            os.environ["PDD_COMPRESS_EXAMPLES"] = "1"
        else:
            os.environ.pop("PDD_CONTEXT_COMPRESSION", None)
            os.environ.pop("PDD_COMPRESS_EXAMPLES", None)
        yield
    finally:
        if previous_mode is None:
            os.environ.pop("PDD_CONTEXT_COMPRESSION", None)
        else:
            os.environ["PDD_CONTEXT_COMPRESSION"] = previous_mode
        if previous_examples is None:
            os.environ.pop("PDD_COMPRESS_EXAMPLES", None)
        else:
            os.environ["PDD_COMPRESS_EXAMPLES"] = previous_examples


def _expanded_prompt_size(*, compress: bool) -> dict[str, int]:
    raw = PROMPT.read_text(encoding="utf-8")
    with _compression_env(compress):
        expanded = preprocess(
            raw,
            recursive=True,
            double_curly_brackets=False,
            compress=compress,
        )
        expanded = preprocess(
            expanded,
            recursive=False,
            double_curly_brackets=True,
            compress=compress,
        )
    return {
        "chars": len(expanded),
        "estimated_tokens": _estimated_tokens(expanded),
    }


def _reset_generated_outputs() -> None:
    """Avoid incremental generate when re-running the benchmark."""
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    for path in GENERATED_DIR.glob("ticket_classifier_*.py"):
        path.unlink(missing_ok=True)


class _FakeHttpResponse:
    """Minimal requests.Response stand-in for cloud POST mocks."""

    status_code = 200
    text = "{}"

    def raise_for_status(self) -> None:
        return None


class _FakeGenerateCodeResponse(_FakeHttpResponse):
    def __init__(
        self,
        payload: dict[str, Any],
        examples_used: list[dict[str, Any]],
        marketplace_context: str,
    ) -> None:
        self._payload = payload
        self._examples_used = examples_used
        self._marketplace_context = marketplace_context

    def json(self) -> dict[str, Any]:
        prompt_content = self._payload["promptContent"]
        final_prompt_chars = len(prompt_content) + len(self._marketplace_context)
        return {
            "generatedCode": _generated_code_from_mold(),
            "totalCost": 0.01 if self._payload.get("compress") else 0.02,
            "modelName": "representative-cloud-model",
            "examplesUsed": self._examples_used,
            "promptStats": {
                "clientPromptChars": len(prompt_content),
                "marketplaceFewShotChars": len(self._marketplace_context),
                "finalPromptChars": final_prompt_chars,
                "finalEstimatedTokens": _estimated_tokens(
                    prompt_content + self._marketplace_context
                ),
            },
        }


class _FakeLlmInvokeResponse(_FakeHttpResponse):
    """Stub llmInvoke so incremental diff analysis falls back to full generate."""

    def json(self) -> dict[str, Any]:
        return {
            "result": {
                "is_big_change": True,
                "change_description": "Demo stub: use full cloud regeneration.",
                "analysis": "Representative marketplace demo routes to generateCode.",
            },
            "totalCost": 0.0,
            "modelName": "representative-cloud-model",
        }


def _is_generate_code_payload(payload: dict[str, Any]) -> bool:
    return "promptContent" in payload


def _is_llm_invoke_payload(payload: dict[str, Any]) -> bool:
    return "prompt" in payload and "inputJson" in payload


def _fake_cloud_post(
    catalog: list[dict[str, Any]],
    examples_used: list[dict[str, Any]],
    payloads: list[dict[str, Any]],
    responses: list[dict[str, Any]],
):
    def fake_post(_url: str, json: dict[str, Any] | None = None, **_kwargs: Any) -> _FakeHttpResponse:
        payload = dict(json or {})
        payloads.append(payload)
        if _is_generate_code_payload(payload):
            compress = bool(payload.get("compress"))
            marketplace_context = _build_marketplace_few_shot_context(
                catalog,
                compress=compress,
            )
            response: _FakeHttpResponse = _FakeGenerateCodeResponse(
                payload,
                examples_used,
                marketplace_context,
            )
        elif _is_llm_invoke_payload(payload):
            response = _FakeLlmInvokeResponse()
        else:
            raise RuntimeError(
                "Unexpected cloud POST payload keys: "
                f"{sorted(payload)} (url={_url!r})"
            )
        responses.append(response.json())
        return response

    return fake_post


def _load_generated_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import generated module at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_behavior(path: Path) -> None:
    module = _load_generated_module(path)
    assert module.classify_ticket("The app crashes when I click Save.") == {
        "category": "bug",
        "severity": "high",
    }
    assert module.classify_ticket("Please add dark mode to the dashboard.") == {
        "category": "feature_request",
        "severity": "medium",
    }
    assert module.classify_ticket("The README is missing install steps.") == {
        "category": "documentation",
        "severity": "low",
    }
    assert module.format_ticket_json("Dashboard feels slow on mobile.") == (
        '{"category": "usability", "severity": "medium"}'
    )


def _latest_evidence(*, prompt_path: Path) -> dict[str, Any]:
    evidence_dir = DEMO_DIR / ".pdd" / "evidence" / "devunits"
    preferred = evidence_dir / f"{_evidence_basename_for_prompt(prompt_path)}.latest.json"
    if preferred.is_file():
        return json.loads(preferred.read_text(encoding="utf-8"))
    evidence_files = sorted(evidence_dir.glob("*.latest.json"))
    if not evidence_files:
        raise RuntimeError("pdd generate did not write an evidence manifest")
    return json.loads(evidence_files[-1].read_text(encoding="utf-8"))


def _stats_from_live_evidence(
    evidence: dict[str, Any],
    *,
    cloud_response: dict[str, Any] | None,
) -> dict[str, Any]:
    """Derive reporting metrics from a real cloud generate evidence manifest."""
    generation = evidence.get("generation") or {}
    prompt_stats = (cloud_response or {}).get("promptStats") or {}
    if prompt_stats:
        return {
            "clientPromptChars": int(prompt_stats.get("clientPromptChars") or 0),
            "finalPromptChars": int(prompt_stats.get("finalPromptChars") or 0),
            "finalEstimatedTokens": int(prompt_stats.get("finalEstimatedTokens") or 0),
            "marketplaceFewShotChars": int(
                prompt_stats.get("marketplaceFewShotChars") or 0
            ),
            "model": generation.get("model") or cloud_response.get("modelName"),
            "cost_usd": generation.get("cost_usd")
            or float(cloud_response.get("totalCost") or 0.0),
        }
    context = evidence.get("context") or {}
    includes = context.get("includes") or []
    include_tokens = sum(int(inc.get("estimated_tokens") or 0) for inc in includes)
    expanded_path = (evidence.get("prompt") or {}).get("expanded_prompt_path")
    expanded_chars = 0
    if expanded_path:
        path = DEMO_DIR / expanded_path
        if path.is_file():
            expanded_chars = len(path.read_text(encoding="utf-8"))
    return {
        "clientPromptChars": expanded_chars,
        "finalPromptChars": expanded_chars + include_tokens * 4,
        "finalEstimatedTokens": _estimated_tokens("x" * expanded_chars) + include_tokens,
        "marketplaceFewShotChars": 0,
        "model": generation.get("model"),
        "cost_usd": generation.get("cost_usd"),
    }


def _is_generate_code_url(url: str) -> bool:
    return "generateCode" in url


def _run_generate(
    *,
    compress: bool,
    catalog: list[dict[str, Any]],
    examples_used: list[dict[str, Any]],
    live: bool,
    prompt_path: Path,
    pin_modules: list[str],
    allow_non_marketplace: bool,
) -> dict[str, Any]:
    output_path = GENERATED_DIR / (
        "ticket_classifier_compressed.py" if compress else "ticket_classifier_uncompressed.py"
    )
    payloads: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    live_cloud_responses: list[dict[str, Any]] = []

    args = [str(prompt_path), "--output", str(output_path), "--evidence"]
    if compress:
        args.append("--compress")

    with ExitStack() as stack:
        stack.enter_context(_compression_env(compress))
        if not live:
            fake_post = _fake_cloud_post(catalog, examples_used, payloads, responses)
            stack.enter_context(
                patch("pdd.core.cloud.CloudConfig.get_jwt_token", return_value="representative-token")
            )
            stack.enter_context(
                patch("pdd.code_generator_main.CloudConfig.is_running_in_cloud", return_value=False)
            )
            stack.enter_context(
                patch(
                    "pdd.code_generator_main.CloudConfig.get_endpoint_url",
                    return_value="https://promptdriven.ai/api/generateCode",
                )
            )
            stack.enter_context(patch("requests.post", side_effect=fake_post))
        else:
            import requests

            real_post = requests.post

            def recording_post(url: str, *args: Any, **kwargs: Any):
                response = real_post(url, *args, **kwargs)
                if _is_generate_code_url(url):
                    try:
                        response.raise_for_status()
                        live_cloud_responses.append(response.json())
                    except (requests.RequestException, json.JSONDecodeError, ValueError):
                        pass
                return response

            stack.enter_context(patch("requests.post", side_effect=recording_post))

        result = CliRunner().invoke(
            generate,
            args,
            obj={
                "force": True,
                "quiet": not live,
                "local": False,
                "temperature": 0.0,
                "strength": 0.5,
                "time": 0.25,
                "context": None,
            },
        )

    if result.exit_code != 0:
        raise RuntimeError(result.output or str(result.exception))

    generate_payloads: list[dict[str, Any]] = []
    generate_responses: list[dict[str, Any]] = []
    if not live:
        generate_payloads = [p for p in payloads if _is_generate_code_payload(p)]
        generate_responses = [r for r in responses if "promptStats" in r]
        if not generate_payloads or not generate_responses:
            raise RuntimeError("representative cloud generateCode path was not invoked")
        if generate_payloads[-1].get("compress") != compress:
            raise RuntimeError("generateCode payload compress flag mismatch")

    _assert_behavior(output_path)
    evidence = _latest_evidence(prompt_path=prompt_path)
    live_cloud_response = live_cloud_responses[-1] if live_cloud_responses else None
    if live and live_cloud_response and live_cloud_response.get("examplesUsed"):
        selected = selected_examples_from_cloud(live_cloud_response["examplesUsed"])
    else:
        selected = evidence["generation"]["grounding"]["selected_examples"]
    grounding_warning: str | None = None
    cloud_model: str | None = None
    cloud_cost: float | None = None
    if live:
        grounding_warning = _validate_live_grounding(
            evidence,
            catalog=catalog,
            pin_modules=pin_modules,
            allow_non_marketplace=allow_non_marketplace,
            selected_examples=selected,
        )
        cloud_stats = _stats_from_live_evidence(
            evidence,
            cloud_response=live_cloud_response,
        )
        expanded = _expanded_prompt_size(compress=compress)
        if not (live_cloud_response or {}).get("promptStats"):
            cloud_stats = {
                **cloud_stats,
                "clientPromptChars": expanded["chars"],
                "finalPromptChars": expanded["chars"],
                "finalEstimatedTokens": expanded["estimated_tokens"],
            }
        prompt_content = "x" * int(cloud_stats.get("clientPromptChars") or expanded["chars"])
        marketplace_chars = int(cloud_stats.get("marketplaceFewShotChars") or 0)
        cloud_model = cloud_stats.get("model")
        cloud_cost = cloud_stats.get("cost_usd")
    else:
        prompt_content = generate_payloads[-1]["promptContent"]
        cloud_stats = generate_responses[-1]["promptStats"]
        marketplace_chars = cloud_stats["marketplaceFewShotChars"]
        mapped = selected_examples_from_cloud(examples_used)
        if not selected or selected[0].get("source") != "marketplace":
            raise RuntimeError("evidence did not record marketplace grounding examples")
        if selected[0].get("module") != mapped[0].get("module"):
            raise RuntimeError("evidence module slug does not match fixture catalog")

    return {
        "mode": "compressed" if compress else "uncompressed",
        "output": str(output_path.relative_to(DEMO_DIR)),
        "client_payload": {
            "chars": len(prompt_content),
            "estimated_tokens": _estimated_tokens(prompt_content),
        },
        "expanded_prompt": _expanded_prompt_size(compress=compress),
        "cloud_prompt_stats": cloud_stats,
        "marketplace_few_shot_chars": marketplace_chars,
        "examples_used": selected,
        "behavior_passed": True,
        "grounding_warning": grounding_warning,
        "marketplace_verified": (
            _live_marketplace_verified(
                selected,
                catalog=catalog,
                pin_modules=pin_modules,
            )[0]
            if live
            else _selected_have_marketplace_source(selected)
        ),
        "cloud_model": cloud_model,
        "cloud_cost_usd": cloud_cost,
    }


def run_demo(
    *,
    live: bool = False,
    allow_non_marketplace: bool = False,
    seed_marketplace: bool = True,
    verbose: bool = False,
) -> dict[str, Any]:
    os.chdir(DEMO_DIR)
    _reset_generated_outputs()
    catalog = _load_marketplace_catalog()
    examples_used = _cloud_examples_used(catalog)
    pin_modules: list[str] = []
    seeded_slugs: list[str] = []
    if live:
        _ensure_cloud_auth()
        pin_modules, seeded_slugs = _pin_modules_for_live(
            catalog,
            seed=seed_marketplace,
            verbose=verbose,
        )
    prompt_path = _prompt_for_run(live=live, pin_modules=pin_modules)
    fixture_few_shot = _fixture_marketplace_few_shot_metrics(catalog)

    uncompressed = _run_generate(
        compress=False,
        catalog=catalog,
        examples_used=examples_used,
        live=live,
        prompt_path=prompt_path,
        pin_modules=pin_modules,
        allow_non_marketplace=allow_non_marketplace,
    )
    compressed = _run_generate(
        compress=True,
        catalog=catalog,
        examples_used=examples_used,
        live=live,
        prompt_path=prompt_path,
        pin_modules=pin_modules,
        allow_non_marketplace=allow_non_marketplace,
    )

    report = {
        "issue": "876",
        "execution_mode": "live" if live else "representative",
        "prompt": str(prompt_path.relative_to(DEMO_DIR)),
        "pin_modules": pin_modules,
        "seeded_cloud_modules": seeded_slugs,
        "fixture_marketplace_few_shot": fixture_few_shot,
        "live_marketplace_strict": live and not allow_non_marketplace,
        "marketplace_fixture": str(MARKETPLACE_EXAMPLES.relative_to(DEMO_DIR)),
        "marketplace_fixture_files": str(MARKETPLACE_FIXTURES.relative_to(DEMO_DIR)),
        "benchmark_criteria": {
            "marketplace_examples_used": "runs[].examples_used[].source == marketplace",
            "generate_path": "pdd generate cloud branch (generateCode payload)",
            "compression_compare": "uncompressed vs --compress on same prompt",
            "size_reduction": "reduction.final_prompt_chars > 0",
            "regeneration_contract": "runs[].behavior_passed == true",
        },
        "runs": [uncompressed, compressed],
        "reduction": {
            "client_prompt_chars": (
                uncompressed["client_payload"]["chars"]
                - compressed["client_payload"]["chars"]
            ),
            "expanded_prompt_chars": (
                uncompressed["expanded_prompt"]["chars"]
                - compressed["expanded_prompt"]["chars"]
            ),
            "final_prompt_chars": (
                uncompressed["cloud_prompt_stats"]["finalPromptChars"]
                - compressed["cloud_prompt_stats"]["finalPromptChars"]
            ),
            "final_estimated_tokens": (
                uncompressed["cloud_prompt_stats"]["finalEstimatedTokens"]
                - compressed["cloud_prompt_stats"]["finalEstimatedTokens"]
            ),
            "marketplace_few_shot_chars": (
                uncompressed.get("marketplace_few_shot_chars", 0)
                - compressed.get("marketplace_few_shot_chars", 0)
            ),
        },
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use real PDD Cloud + model (requires pdd auth login). Not for CI.",
    )
    parser.add_argument(
        "--allow-non-marketplace",
        action="store_true",
        help="Live only: warn instead of failing when cloud examples lack source=marketplace.",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Live only: skip submitExample seeding of catalog fixtures before generate.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print seeding and pin resolution details to stderr.",
    )
    args = parser.parse_args(argv)
    live = args.live or os.environ.get("PDD_MARKETPLACE_DEMO_LIVE", "").lower() in (
        "1",
        "true",
        "yes",
    )
    allow_non_marketplace = args.allow_non_marketplace or os.environ.get(
        "PDD_MARKETPLACE_DEMO_ALLOW_NON_MARKETPLACE",
        "",
    ).lower() in ("1", "true", "yes")

    report = run_demo(
        live=live,
        allow_non_marketplace=allow_non_marketplace,
        seed_marketplace=not args.no_seed,
        verbose=args.verbose,
    )
    before, after = report["runs"]
    print("=== Marketplace compression regeneration demo ===")
    print(f"Execution mode: {report['execution_mode']}")
    print(f"Prompt: {report['prompt']}")
    print(f"Marketplace catalog: {report['marketplace_fixture']}")
    fixture_fs = report.get("fixture_marketplace_few_shot") or {}
    if fixture_fs:
        print(
            "Fixture marketplace few-shot (local #876 compress path): "
            f"{fixture_fs['uncompressed_chars']} -> {fixture_fs['compressed_chars']} chars "
            f"({fixture_fs['reduction_chars']} saved)"
        )
    if report.get("pin_modules"):
        print(f"Live pins: {', '.join(report['pin_modules'])}")
    if report["execution_mode"] == "representative":
        print(
            "Uncompressed final prompt: "
            f"{before['cloud_prompt_stats']['finalPromptChars']} chars / "
            f"{before['cloud_prompt_stats']['finalEstimatedTokens']} est. tokens"
        )
        print(
            "Compressed final prompt: "
            f"{after['cloud_prompt_stats']['finalPromptChars']} chars / "
            f"{after['cloud_prompt_stats']['finalEstimatedTokens']} est. tokens"
        )
        print(
            "Reduction: "
            f"{report['reduction']['final_prompt_chars']} chars / "
            f"{report['reduction']['final_estimated_tokens']} est. tokens "
            f"(marketplace few-shot -{report['reduction']['marketplace_few_shot_chars']} chars)"
        )
    else:
        print(
            "Live expanded prompt: "
            f"{before['expanded_prompt']['chars']} -> {after['expanded_prompt']['chars']} chars "
            f"({report['reduction']['expanded_prompt_chars']} saved)"
        )
        print(
            f"Cloud model: {after.get('cloud_model')} | "
            f"cost (compressed run): ${after.get('cloud_cost_usd')}"
        )
        for run in (before, after):
            if run.get("grounding_warning"):
                print(f"Warning ({run['mode']}): {run['grounding_warning']}")
    print("Cloud examples used (from evidence):")
    for example in after["examples_used"]:
        source = example.get("source") or "unknown"
        print(f"  - {example['module']} ({example.get('title', 'untitled')}) [{source}]")
    if report["execution_mode"] == "live":
        verified, reason = _live_marketplace_verified(
            after["examples_used"],
            catalog=_load_marketplace_catalog(),
            pin_modules=report.get("pin_modules") or [],
        )
        if verified:
            print(f"Marketplace few-shot (cloud): VERIFIED ({reason})")
        elif report.get("live_marketplace_strict"):
            print("Marketplace few-shot (cloud): FAILED strict check")
        else:
            print(
                "Marketplace few-shot (cloud): not verified "
                "(use default run_demo.py for representative marketplace proof)"
            )
    print("Behavior checks: PASS")
    print(f"Report: {REPORT_PATH.relative_to(DEMO_DIR)}")
    print("See examples/BENCHMARK_876.md for review mapping.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
