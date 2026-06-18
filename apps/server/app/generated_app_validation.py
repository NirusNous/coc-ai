from __future__ import annotations

import json
import re
from pathlib import PurePosixPath

from app.models import ArchitectureSpec, GeneratedAppSpec, GeneratedFile, RequirementsSpec


class GeneratedAppValidationError(ValueError):
    pass


ALLOWED_ROOT_FILES = {
    "package.json",
    "index.html",
    "tsconfig.json",
    "tsconfig.app.json",
    "tsconfig.node.json",
    "vite.config.ts",
    "vite.config.js",
    "vite.config.mjs",
    "vite.config.mts",
    "eslint.config.js",
    "eslint.config.mjs",
    "postcss.config.js",
    "postcss.config.cjs",
    "tailwind.config.js",
    "tailwind.config.cjs",
    "tailwind.config.ts",
}
ALLOWED_PATH_PREFIXES = ("src/", "public/")
REQUIRED_FILES = {
    "package.json",
    "index.html",
    "src/main.tsx",
}
REQUIRED_PACKAGES = {
    "react",
    "react-dom",
    "vite",
    "typescript",
    "@vitejs/plugin-react",
    "@types/react",
    "@types/react-dom",
}
BANNED_PACKAGES = {
    "fastapi",
    "express",
    "fastify",
    "koa",
    "hapi",
    "nestjs",
    "next",
    "nuxt",
    "prisma",
    "sequelize",
    "typeorm",
    "pg",
    "postgres",
    "mysql",
    "mysql2",
    "sqlite",
    "sqlite3",
    "better-sqlite3",
    "mongoose",
    "mongodb",
    "drizzle-orm",
    "shelljs",
    "zx",
    "execa",
    "tsx",
    "ts-node",
    "nodemon",
}
BANNED_SCRIPT_NAMES = {
    "preinstall",
    "install",
    "postinstall",
    "prepublish",
    "postpublish",
    "prepare",
}
ALLOWED_SCRIPTS = {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
}
BANNED_SOURCE_SNIPPETS = (
    'from "fs"',
    "from 'fs'",
    'from "path"',
    "from 'path'",
    'from "child_process"',
    "from 'child_process'",
    'from "express"',
    "from 'express'",
    'from "fastify"',
    "from 'fastify'",
    'from "koa"',
    "from 'koa'",
    'require("fs")',
    "require('fs')",
    'require("path")',
    "require('path')",
    'require("child_process")',
    "require('child_process')",
    'require("express")',
    "require('express')",
    "process.env",
    "FastAPI(",
)
META_APP_PHRASES = (
    "fallback prototype",
    "feature checklist",
    "original prompt",
    "requirements json",
    "architecture json",
    "validated requirements",
    "planned ui responsibilities",
    "captured for traceability",
)
NOTE_APP_PHRASES = (
    "notepad",
    "notes app",
)


def _normalize_path(path: str) -> str:
    normalized_path = path.replace("\\", "/").strip()

    if not normalized_path:
        raise GeneratedAppValidationError("Generated file path cannot be empty.")

    pure_path = PurePosixPath(normalized_path)

    if pure_path.is_absolute():
        raise GeneratedAppValidationError(
            f"Absolute generated file paths are not allowed: {path}"
        )

    for part in pure_path.parts:
        if part in ("", ".", ".."):
            raise GeneratedAppValidationError(
                f"Unsafe generated file path segment in: {path}"
            )

        if ":" in part:
            raise GeneratedAppValidationError(
                f"Generated file path contains an unsafe character: {path}"
            )

        if part.startswith("."):
            raise GeneratedAppValidationError(
                f"Hidden or dot-prefixed generated file paths are not allowed: {path}"
            )

    normalized = str(pure_path).replace("\\", "/")

    if normalized in ALLOWED_ROOT_FILES:
        return normalized

    if normalized.startswith(ALLOWED_PATH_PREFIXES):
        return normalized

    raise GeneratedAppValidationError(
        f"Generated file path is outside the allowed frontend app surface: {path}"
    )


def _normalize_script_value(value: str) -> str:
    return " ".join(value.strip().split())


def _validate_package_json(content: str) -> str:
    try:
        package_json = json.loads(content)
    except json.JSONDecodeError as error:
        raise GeneratedAppValidationError("Generated package.json is not valid JSON.") from error

    if not isinstance(package_json, dict):
        raise GeneratedAppValidationError("Generated package.json must contain a JSON object.")

    name = package_json.get("name")

    if not isinstance(name, str) or not name.strip():
        raise GeneratedAppValidationError("Generated package.json must include a non-empty name.")

    if package_json.get("private") is not True:
        raise GeneratedAppValidationError("Generated package.json must set private to true.")

    scripts = package_json.get("scripts")

    if not isinstance(scripts, dict):
        raise GeneratedAppValidationError("Generated package.json must include a scripts object.")

    banned_script_names = sorted(script for script in scripts if script in BANNED_SCRIPT_NAMES)

    if banned_script_names:
        raise GeneratedAppValidationError(
            f"Generated package.json contains banned scripts: {', '.join(banned_script_names)}."
        )

    unexpected_scripts = sorted(set(scripts) - set(ALLOWED_SCRIPTS))

    if unexpected_scripts:
        raise GeneratedAppValidationError(
            "Generated package.json may only include dev, build, and preview scripts."
        )

    for script_name, expected_value in ALLOWED_SCRIPTS.items():
        raw_value = scripts.get(script_name)

        if not isinstance(raw_value, str):
            raise GeneratedAppValidationError(
                f"Generated package.json is missing the {script_name} script."
            )

        normalized_value = _normalize_script_value(raw_value)

        if normalized_value != expected_value:
            raise GeneratedAppValidationError(
                f"Generated package.json script {script_name} must be exactly '{expected_value}'."
            )

    dependencies = package_json.get("dependencies") or {}
    dev_dependencies = package_json.get("devDependencies") or {}

    if not isinstance(dependencies, dict) or not isinstance(dev_dependencies, dict):
        raise GeneratedAppValidationError(
            "Generated package.json dependencies and devDependencies must be objects."
        )

    all_dependencies = set(dependencies) | set(dev_dependencies)
    missing_packages = sorted(REQUIRED_PACKAGES - all_dependencies)

    if missing_packages:
        raise GeneratedAppValidationError(
            f"Generated package.json is missing required packages: {', '.join(missing_packages)}."
        )

    banned_packages = sorted(package for package in all_dependencies if package in BANNED_PACKAGES)

    if banned_packages:
        raise GeneratedAppValidationError(
            f"Generated package.json contains banned packages: {', '.join(banned_packages)}."
        )

    return json.dumps(package_json, indent=2) + "\n"


def _validate_source_content(file: GeneratedFile) -> None:
    if not file.path.endswith((".ts", ".tsx", ".js", ".jsx")):
        return

    for snippet in BANNED_SOURCE_SNIPPETS:
        if snippet in file.content:
            raise GeneratedAppValidationError(
                f"Generated source file {file.path} contains a disallowed backend or runtime snippet."
            )


def _normalize_freeform_text(value: str) -> str:
    return " ".join(re.split(r"[^a-z0-9]+", value.casefold())).strip()


def _plan_supports_note_taking(
    requirements: RequirementsSpec | None,
    architecture: ArchitectureSpec | None,
) -> bool:
    plan_fragments: list[str] = []

    if requirements is not None:
        plan_fragments.append(requirements.appName)
        plan_fragments.append(requirements.summary)
        plan_fragments.extend(requirements.features)
        plan_fragments.extend(requirements.constraints)

    if architecture is not None:
        plan_fragments.extend(component.name for component in architecture.components)
        plan_fragments.extend(
            component.responsibility for component in architecture.components
        )
        plan_fragments.extend(model.name for model in architecture.dataModels)
        plan_fragments.extend(
            field.name
            for model in architecture.dataModels
            for field in model.fields
        )

    normalized_plan = _normalize_freeform_text(" ".join(plan_fragments))
    note_keywords = (
        "note",
        "notes",
        "comment",
        "comments",
        "journal",
        "memo",
        "markdown",
        "editor",
        "writing",
    )
    return any(keyword in normalized_plan for keyword in note_keywords)


def _validate_plan_alignment(
    files: list[GeneratedFile],
    requirements: RequirementsSpec | None,
    architecture: ArchitectureSpec | None,
) -> None:
    # The model sometimes drifts into a meta app that restates the plan instead
    # of implementing the approved product. Reject those outputs early here.
    source_bundle = "\n".join(
        file.content
        for file in files
        if file.path.endswith((".ts", ".tsx", ".js", ".jsx", ".html"))
    )
    normalized_source = _normalize_freeform_text(source_bundle)

    meta_hits = [
        phrase for phrase in META_APP_PHRASES if phrase in normalized_source
    ]

    if meta_hits:
        raise GeneratedAppValidationError(
            "Generated app mirrors the plan instead of implementing the product workflow."
        )

    if architecture is not None:
        component_names = [
            _normalize_freeform_text(component.name)
            for component in architecture.components
            if component.name.strip()
        ]
        component_names = [
            name
            for name in component_names
            if name and name not in {"app", "app shell", "shell", "layout"}
        ]

        if component_names and not any(
            component_name in normalized_source for component_name in component_names
        ):
            raise GeneratedAppValidationError(
                "Generated app does not appear to implement the approved architecture components."
            )

        specific_field_names = [
            _normalize_freeform_text(field.name)
            for model in architecture.dataModels
            for field in model.fields
            if field.name.strip().casefold()
            not in {"id", "title", "name", "label", "description"}
        ]

        if specific_field_names and not any(
            field_name in normalized_source for field_name in specific_field_names
        ):
            raise GeneratedAppValidationError(
                "Generated app does not appear to use the approved data model fields."
            )

    if not _plan_supports_note_taking(requirements, architecture):
        if any(phrase in normalized_source for phrase in NOTE_APP_PHRASES):
            raise GeneratedAppValidationError(
                "Generated app changed the product into an unrelated note-taking interface."
            )


def validate_generated_app_spec(
    app_spec: GeneratedAppSpec,
    *,
    requirements: RequirementsSpec | None = None,
    architecture: ArchitectureSpec | None = None,
) -> GeneratedAppSpec:
    files = app_spec.files

    if not files:
        raise GeneratedAppValidationError("Code Generation Agent returned no files.")

    if len(files) > 24:
        raise GeneratedAppValidationError("Generated app contains too many files for this prototype.")

    seen_paths: set[str] = set()
    normalized_files: list[GeneratedFile] = []

    for generated_file in files:
        normalized_path = _normalize_path(generated_file.path)

        if normalized_path in seen_paths:
            raise GeneratedAppValidationError(
                f"Generated app contains duplicate file path: {normalized_path}"
            )

        if not generated_file.content.strip():
            raise GeneratedAppValidationError(
                f"Generated file content cannot be empty: {normalized_path}"
            )

        normalized_file = GeneratedFile(
            path=normalized_path,
            content=generated_file.content,
        )

        _validate_source_content(normalized_file)

        if normalized_path == "package.json":
            normalized_file = GeneratedFile(
                path="package.json",
                content=_validate_package_json(generated_file.content),
            )

        normalized_files.append(normalized_file)
        seen_paths.add(normalized_path)

    missing_required_files = sorted(REQUIRED_FILES - seen_paths)

    if missing_required_files:
        raise GeneratedAppValidationError(
            f"Generated app is missing required files: {', '.join(missing_required_files)}."
        )

    index_html = next((file for file in normalized_files if file.path == "index.html"), None)

    if index_html is not None and "/src/main.tsx" not in index_html.content:
        raise GeneratedAppValidationError(
            "Generated index.html must load /src/main.tsx."
        )

    _validate_plan_alignment(
        normalized_files,
        requirements=requirements,
        architecture=architecture,
    )

    return GeneratedAppSpec(files=normalized_files)
