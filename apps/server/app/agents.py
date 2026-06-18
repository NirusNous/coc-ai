import json
import re
from typing import Awaitable, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from app.agent_prompts import (
    build_code_generation_messages,
    build_debug_messages,
    build_patch_messages,
    build_architecture_messages,
    build_requirements_messages,
)
from app.config import get_llm_settings
from app.generated_app_validation import GeneratedAppValidationError, validate_generated_app_spec
from app.llm_client import LLMClient, LLMClientError
from app.models import (
    ArchitectureSpec,
    ComponentSpec,
    DebugAnalysisSpec,
    FieldSpec,
    DataModelSpec,
    GeneratedAppSpec,
    GeneratedFile,
    RequirementsSpec,
    StackSpec,
)


AgentLogger = Callable[[str], Awaitable[None]]
TModel = TypeVar("TModel", bound=BaseModel)


def _clean_prompt(prompt: str) -> str:
    return " ".join(prompt.strip().split())


def _title_case_phrase(value: str) -> str:
    titled = value.title()
    return re.sub(r"\bAi\b", "AI", titled)


def _extract_app_name(prompt: str) -> str:
    cleaned_prompt = _clean_prompt(prompt)

    if not cleaned_prompt:
        return "Agentic OS App"

    candidate = re.sub(
        r"^(build|create|make|generate|design)\s+",
        "",
        cleaned_prompt,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(r"^(a|an|the)\s+", "", candidate, flags=re.IGNORECASE)
    candidate = re.split(
        r"\b(with|for|that|which|using)\b|[.:,;]",
        candidate,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    candidate = re.sub(
        r"\b(app|application|tool|dashboard|website|site|prototype)\b",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = " ".join(candidate.split()).strip(" -")

    if not candidate:
        return "Agentic OS App"

    return _title_case_phrase(candidate)


def _extract_feature_candidates(prompt: str) -> list[str]:
    cleaned_prompt = _clean_prompt(prompt)
    feature_matches = re.findall(
        r"\bwith\b\s+([^.;]+)",
        cleaned_prompt,
        flags=re.IGNORECASE,
    )
    candidates: list[str] = []

    for match in feature_matches:
        parts = re.split(r",|\band\b", match, flags=re.IGNORECASE)

        for part in parts:
            candidate = re.sub(
                r"^(a|an|the)\s+",
                "",
                part.strip(),
                flags=re.IGNORECASE,
            )

            if candidate:
                candidates.append(candidate)

    deduped: list[str] = []

    for candidate in candidates:
        normalized = candidate.casefold()

        if normalized not in [item.casefold() for item in deduped]:
            deduped.append(candidate)

    return deduped


def _build_feature_list(prompt: str, app_name: str) -> list[str]:
    candidates = _extract_feature_candidates(prompt)

    if candidates:
        return [_title_case_phrase(candidate) for candidate in candidates[:6]]

    base_name = app_name.lower()
    return [
        f"Capture and manage {base_name} data in the browser",
        f"Review and update the main {base_name} workflow",
        f"Keep the prototype fully client-side with local state",
    ]


def _extract_entity_name(prompt: str, app_name: str) -> str:
    cleaned_prompt = _clean_prompt(prompt)
    match = re.search(
        r"\bfor\s+(?:tracking|managing|organizing|reviewing|planning)\s+([a-zA-Z][a-zA-Z\s-]{2,40})",
        cleaned_prompt,
        flags=re.IGNORECASE,
    )

    if match:
        entity_phrase = re.split(
            r"\b(with|using|in|across)\b|[.;,]",
            match.group(1),
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()
        entity_words = entity_phrase.split()

        if entity_words:
            candidate = entity_words[-1].rstrip("s")

            if candidate:
                return _title_case_phrase(candidate)

    app_words = [
        word
        for word in re.split(r"[^a-zA-Z0-9]+", app_name)
        if word and word.casefold() not in {"app", "tool", "dashboard", "board"}
    ]

    if app_words:
        return _title_case_phrase(app_words[-1].rstrip("s"))

    return "Item"


def _build_fallback_data_fields(features: list[str]) -> list[FieldSpec]:
    joined_features = " ".join(features).casefold()
    fields = [
        FieldSpec(name="id", type="string", required=True),
        FieldSpec(name="title", type="string", required=True),
    ]

    if any(keyword in joined_features for keyword in ("stage", "status", "column", "lane")):
        fields.append(FieldSpec(name="stage", type="string", required=True))

    if any(keyword in joined_features for keyword in ("note", "notes", "comment", "comments")):
        fields.append(FieldSpec(name="notes", type="string", required=False))

    if any(keyword in joined_features for keyword in ("rating", "ratings", "score", "scores")):
        fields.append(FieldSpec(name="rating", type="number", required=False))

    if any(keyword in joined_features for keyword in ("deadline", "due date", "due", "schedule")):
        fields.append(FieldSpec(name="dueDate", type="string", required=False))

    if any(keyword in joined_features for keyword in ("complete", "completed", "done")):
        fields.append(FieldSpec(name="completed", type="boolean", required=False))

    return fields


def _build_fallback_components(app_name: str, features: list[str]) -> list[ComponentSpec]:
    components = [
        ComponentSpec(
            name="AppShell",
            responsibility=f"Owns the {app_name} experience and coordinates local UI state.",
        ),
        ComponentSpec(
            name="FeatureOverview",
            responsibility="Summarizes the primary workflow and key feature areas for the prototype.",
        ),
    ]

    for feature in features[:3]:
        words = [part for part in re.split(r"[^a-zA-Z0-9]+", feature) if part]

        if not words:
            continue

        component_name = f"{''.join(word.capitalize() for word in words)}Panel"
        components.append(
            ComponentSpec(
                name=component_name,
                responsibility=f"Handles the '{feature}' part of the workflow.",
            )
        )

    return components


def _build_fallback_requirements_spec(prompt: str) -> RequirementsSpec:
    app_name = _extract_app_name(prompt)
    features = _build_feature_list(prompt, app_name)

    return RequirementsSpec(
        appName=app_name,
        summary=f"Local frontend prototype for {app_name} derived from the prompt.",
        features=features,
        constraints=[
            "Use React",
            "Use TypeScript",
            "Use Vite",
            "Use client-side state only",
            "Do not require authentication",
            "Do not require a database",
            "Preserve the user prompt intent when the LLM fallback path is used",
        ],
    )


def _build_fallback_architecture_spec(
    prompt: str,
    requirements: RequirementsSpec,
) -> ArchitectureSpec:
    entity_name = _extract_entity_name(prompt, requirements.appName)

    return ArchitectureSpec(
        stack=StackSpec(
            frontend="React",
            language="TypeScript",
            buildTool="Vite",
            styling="CSS",
            stateManagement="React useState",
        ),
        components=_build_fallback_components(
            requirements.appName,
            requirements.features,
        ),
        dataModels=[
            DataModelSpec(
                name=entity_name,
                fields=_build_fallback_data_fields(requirements.features),
            )
        ],
    )


def _slugify_app_name(app_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", app_name.lower()).strip("-")

    if not slug:
        return "agentic-os-app"

    return slug


def _humanize_identifier(value: str) -> str:
    parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", value.replace("-", " "))

    if not parts:
        return "Field"

    return " ".join(part.upper() if part.isupper() else part.capitalize() for part in parts)


def _sanitize_component_name(name: str, fallback: str) -> str:
    parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", name.replace("-", " "))
    candidate = "".join(part[:1].upper() + part[1:] for part in parts if part)

    if not candidate or not candidate[0].isalpha():
        return fallback

    return candidate


def _normalize_field_type(field_type: str) -> str:
    normalized = field_type.casefold()

    if "bool" in normalized:
        return "boolean"

    if any(token in normalized for token in ("number", "int", "float", "decimal", "score", "count")):
        return "number"

    return "string"


def _build_primary_data_model(
    requirements: RequirementsSpec,
    architecture: ArchitectureSpec,
) -> DataModelSpec:
    if architecture.dataModels:
        source_model = architecture.dataModels[0]
        normalized_fields = [
            FieldSpec(
                name=field.name.strip() or "field",
                type=_normalize_field_type(field.type),
                required=field.required,
            )
            for field in source_model.fields
            if field.name.strip()
        ]
    else:
        normalized_fields = _build_fallback_data_fields(requirements.features)
        source_model = DataModelSpec(
            name=_extract_entity_name(requirements.appName, requirements.appName),
            fields=normalized_fields,
        )

    field_names = {field.name.casefold() for field in normalized_fields}

    if "id" not in field_names:
        normalized_fields.insert(0, FieldSpec(name="id", type="string", required=True))

    if not any(name in field_names for name in {"title", "name", "label"}):
        insert_index = 1 if normalized_fields and normalized_fields[0].name == "id" else 0
        normalized_fields.insert(
            insert_index,
            FieldSpec(name="title", type="string", required=True),
        )

    return DataModelSpec(
        name=source_model.name.strip() or "Item",
        fields=normalized_fields,
    )


def _build_fallback_field_definitions(model: DataModelSpec) -> list[dict[str, object]]:
    return [
        {
            "name": field.name,
            "label": _humanize_identifier(field.name),
            "type": _normalize_field_type(field.type),
            "required": field.required,
        }
        for field in model.fields
    ]


def _sample_value_for_field(
    field_name: str,
    field_type: str,
    *,
    index: int,
    model_name: str,
    feature_seed: list[str],
) -> object:
    normalized_name = field_name.casefold()
    feature_text = feature_seed[index % len(feature_seed)] if feature_seed else f"{model_name} workflow"

    if normalized_name == "id":
        return f"{_slugify_app_name(model_name)}-{index + 1}"

    if field_type == "boolean":
        return index % 2 == 0

    if field_type == "number":
        if "score" in normalized_name or "rating" in normalized_name:
            return 3 + index

        if "estimate" in normalized_name or "hours" in normalized_name:
            return 2 + (index * 2)

        return index + 1

    if any(token in normalized_name for token in ("title", "name", "label")):
        return f"{model_name} {index + 1}"

    if any(token in normalized_name for token in ("status", "stage", "column", "lane")):
        return ["Backlog", "In Progress", "Ready", "Done"][index % 4]

    if any(token in normalized_name for token in ("priority", "severity", "level")):
        return ["High", "Medium", "Low"][index % 3]

    if any(token in normalized_name for token in ("category", "type")):
        return ["Core", "Secondary", "Review"][index % 3]

    if any(token in normalized_name for token in ("owner", "assignee", "person", "lead")):
        return ["Alex", "Jordan", "Sam"][index % 3]

    if "email" in normalized_name:
        return f"user{index + 1}@example.com"

    if any(token in normalized_name for token in ("date", "deadline", "due", "schedule")):
        return f"2026-06-{20 + index:02d}"

    if any(token in normalized_name for token in ("description", "details", "summary", "notes", "comment")):
        return feature_text

    return feature_text


def _build_sample_records(
    model: DataModelSpec,
    requirements: RequirementsSpec,
) -> list[dict[str, object]]:
    feature_seed = requirements.features[:3] or [requirements.summary or requirements.appName]
    records: list[dict[str, object]] = []

    for index in range(3):
        record: dict[str, object] = {}

        for field in model.fields:
            record[field.name] = _sample_value_for_field(
                field.name,
                _normalize_field_type(field.type),
                index=index,
                model_name=model.name,
                feature_seed=feature_seed,
            )

        records.append(record)

    return records


def _build_fallback_generated_app(
    prompt: str,
    requirements: RequirementsSpec,
    architecture: ArchitectureSpec,
) -> GeneratedAppSpec:
    app_name = requirements.appName.strip() or "Agentic OS App"
    package_name = _slugify_app_name(app_name)
    primary_model = _build_primary_data_model(requirements, architecture)
    field_definitions = _build_fallback_field_definitions(primary_model)
    sample_records = _build_sample_records(primary_model, requirements)
    record_label = primary_model.name.strip() or "Item"

    component_names = architecture.components
    app_shell_component = _sanitize_component_name(
        component_names[0].name if len(component_names) > 0 else "AppShell",
        "AppShell",
    )
    overview_component = _sanitize_component_name(
        component_names[1].name if len(component_names) > 1 else "OverviewPanel",
        "OverviewPanel",
    )
    workspace_component = _sanitize_component_name(
        component_names[2].name if len(component_names) > 2 else "WorkspacePanel",
        "WorkspacePanel",
    )
    editor_component = _sanitize_component_name(
        component_names[3].name if len(component_names) > 3 else "EditorPanel",
        "EditorPanel",
    )
    overview_title = component_names[1].name if len(component_names) > 1 else "Overview"
    overview_subtitle = (
        component_names[1].responsibility
        if len(component_names) > 1
        else f"Track {record_label.lower()} progress and current activity."
    )
    workspace_title = component_names[2].name if len(component_names) > 2 else f"{record_label} Workspace"
    workspace_subtitle = (
        component_names[2].responsibility
        if len(component_names) > 2
        else f"Browse, search, and organize {record_label.lower()} records."
    )
    editor_title = component_names[3].name if len(component_names) > 3 else f"Edit {record_label}"
    editor_subtitle = (
        component_names[3].responsibility
        if len(component_names) > 3
        else f"Create and update {record_label.lower()} records in local state."
    )

    app_name_json = json.dumps(app_name)
    summary_json = json.dumps(requirements.summary)
    record_label_json = json.dumps(record_label)
    storage_key_json = json.dumps(f"agentic-os::{package_name}::records")
    field_definitions_json = json.dumps(field_definitions, indent=2)
    sample_records_json = json.dumps(sample_records, indent=2)
    overview_title_json = json.dumps(overview_title)
    overview_subtitle_json = json.dumps(overview_subtitle)
    workspace_title_json = json.dumps(workspace_title)
    workspace_subtitle_json = json.dumps(workspace_subtitle)
    editor_title_json = json.dumps(editor_title)
    editor_subtitle_json = json.dumps(editor_subtitle)

    package_json = {
        "name": package_name,
        "private": True,
        "version": "0.0.0",
        "type": "module",
        "scripts": {
            "dev": "vite",
            "build": "vite build",
            "preview": "vite preview",
        },
        "dependencies": {
            "react": "^19.2.6",
            "react-dom": "^19.2.6",
        },
        "devDependencies": {
            "@types/react": "^19.2.14",
            "@types/react-dom": "^19.2.3",
            "@vitejs/plugin-react": "^6.0.1",
            "typescript": "~6.0.2",
            "vite": "^8.0.12",
        },
    }

    return GeneratedAppSpec(
        files=[
            GeneratedFile(
                path="package.json",
                content=json.dumps(package_json, indent=2) + "\n",
            ),
            GeneratedFile(
                path="index.html",
                content="""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Agentic OS Preview</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
""",
            ),
            GeneratedFile(
                path="tsconfig.json",
                content="""{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
""",
            ),
            GeneratedFile(
                path="tsconfig.app.json",
                content="""{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src"]
}
""",
            ),
            GeneratedFile(
                path="tsconfig.node.json",
                content="""{
  "compilerOptions": {
    "composite": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
""",
            ),
            GeneratedFile(
                path="vite.config.ts",
                content="""import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
});
""",
            ),
            GeneratedFile(
                path="src/main.tsx",
                content="""import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
""",
            ),
            GeneratedFile(
                path="src/App.tsx",
                content=f"""import {{
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
}} from "react";

type DataField = {{
  name: string;
  label: string;
  type: "string" | "number" | "boolean";
  required: boolean;
}};

type ItemRecord = {{
  id: string;
  [key: string]: string | number | boolean;
}};

type SectionProps = {{
  title: string;
  subtitle: string;
  children: ReactNode;
}};

type WorkspaceProps = {{
  title: string;
  subtitle: string;
  records: ItemRecord[];
  titleFieldName: string;
  statusFieldName: string | null;
  booleanFieldName: string | null;
  query: string;
  selectedStatus: string;
  viewMode: "list" | "board";
  onQueryChange: (value: string) => void;
  onStatusChange: (value: string) => void;
  onViewModeChange: (value: "list" | "board") => void;
  onSelectRecord: (record: ItemRecord) => void;
}};

type EditorProps = {{
  title: string;
  subtitle: string;
  draft: ItemRecord;
  editableFields: DataField[];
  isEditing: boolean;
  onChangeField: (field: DataField, value: string | boolean) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onDelete: () => void;
  onReset: () => void;
}};

const appName = {app_name_json};
const summary = {summary_json};
const recordLabel = {record_label_json};
const storageKey = {storage_key_json};
const fieldDefinitions = {field_definitions_json} as DataField[];
const seedRecords = {sample_records_json} as ItemRecord[];
const editableFields = fieldDefinitions.filter((field) => field.name !== "id");
const titleFieldName =
  editableFields.find((field) =>
    ["title", "name", "label"].includes(field.name.toLowerCase()),
  )?.name ?? editableFields[0]?.name ?? "title";
const statusFieldName =
  editableFields.find((field) =>
    ["status", "stage", "column", "lane"].includes(field.name.toLowerCase()),
  )?.name ?? null;
const booleanFieldName =
  editableFields.find((field) =>
    ["completed", "done", "active", "archived"].includes(field.name.toLowerCase()) ||
    field.type === "boolean",
  )?.name ?? null;

function createId() {{
  return `${{storageKey}}-${{Math.random().toString(36).slice(2, 9)}}`;
}}

function getDefaultValue(field: DataField): string | number | boolean {{
  if (field.type === "boolean") {{
    return false;
  }}

  if (field.type === "number") {{
    return 0;
  }}

  return "";
}}

function normalizeFieldValue(
  field: DataField,
  value: unknown,
): string | number | boolean {{
  if (field.type === "boolean") {{
    return typeof value === "boolean" ? value : false;
  }}

  if (field.type === "number") {{
    const parsed =
      typeof value === "number"
        ? value
        : typeof value === "string"
          ? Number(value)
          : Number.NaN;

    return Number.isFinite(parsed) ? parsed : 0;
  }}

  return typeof value === "string" ? value : value == null ? "" : String(value);
}}

function createEmptyRecord(): ItemRecord {{
  const nextRecord: ItemRecord = {{ id: createId() }};

  editableFields.forEach((field) => {{
    nextRecord[field.name] = getDefaultValue(field);
  }});

  return nextRecord;
}}

function normalizeRecord(value: Record<string, unknown>): ItemRecord {{
  const normalized: ItemRecord = {{
    id: typeof value.id === "string" && value.id ? value.id : createId(),
  }};

  editableFields.forEach((field) => {{
    normalized[field.name] = normalizeFieldValue(field, value[field.name]);
  }});

  return normalized;
}}

function readInitialRecords(): ItemRecord[] {{
  try {{
    const rawValue = window.localStorage.getItem(storageKey);

    if (!rawValue) {{
      return seedRecords.map((record) => normalizeRecord(record));
    }}

    const parsed: unknown = JSON.parse(rawValue);

    if (!Array.isArray(parsed)) {{
      return seedRecords.map((record) => normalizeRecord(record));
    }}

    return parsed
      .filter((entry): entry is Record<string, unknown> => Boolean(entry) && typeof entry === "object")
      .map((entry) => normalizeRecord(entry));
  }} catch {{
    return seedRecords.map((record) => normalizeRecord(record));
  }}
}}

function formatRecordValue(value: string | number | boolean): string {{
  if (typeof value === "boolean") {{
    return value ? "Yes" : "No";
  }}

  return String(value);
}}

function matchesQuery(record: ItemRecord, query: string): boolean {{
  if (!query.trim()) {{
    return true;
  }}

  const normalizedQuery = query.trim().toLowerCase();

  return editableFields.some((field) =>
    formatRecordValue(record[field.name] ?? "").toLowerCase().includes(normalizedQuery),
  );
}}

function Panel({{ title, subtitle, children }}: SectionProps) {{
  return (
    <section className="panel">
      <div className="panelHeader">
        <div>
          <h2>{{title}}</h2>
          <p>{{subtitle}}</p>
        </div>
      </div>
      {{children}}
    </section>
  );
}}

function {app_shell_component}({{ children }}: {{ children: ReactNode }}) {{
  return <main className="appShell">{{children}}</main>;
}}

function {overview_component}({{
  totalCount,
  visibleCount,
  completedCount,
  stageCount,
}}: {{
  totalCount: number;
  visibleCount: number;
  completedCount: number;
  stageCount: number;
}}) {{
  return (
    <Panel title={overview_title_json} subtitle={overview_subtitle_json}>
      <div className="metricGrid">
        <article className="metricCard">
          <span>Total</span>
          <strong>{{totalCount}}</strong>
        </article>
        <article className="metricCard">
          <span>Visible</span>
          <strong>{{visibleCount}}</strong>
        </article>
        <article className="metricCard">
          <span>Completed</span>
          <strong>{{completedCount}}</strong>
        </article>
        <article className="metricCard">
          <span>Stages</span>
          <strong>{{stageCount}}</strong>
        </article>
      </div>
    </Panel>
  );
}}

function {workspace_component}({{
  title,
  subtitle,
  records,
  titleFieldName: currentTitleFieldName,
  statusFieldName: currentStatusFieldName,
  booleanFieldName: currentBooleanFieldName,
  query,
  selectedStatus,
  viewMode,
  onQueryChange,
  onStatusChange,
  onViewModeChange,
  onSelectRecord,
}}: WorkspaceProps) {{
  const availableStatuses = useMemo(() => {{
    if (!currentStatusFieldName) {{
      return [];
    }}

    return Array.from(
      new Set(records.map((record) => formatRecordValue(record[currentStatusFieldName] ?? ""))),
    ).filter(Boolean);
  }}, [records, currentStatusFieldName]);

  const groupedRecords = useMemo(() => {{
    if (!currentStatusFieldName) {{
      return [];
    }}

    return availableStatuses.map((status) => ({{
      status,
      records: records.filter(
        (record) => formatRecordValue(record[currentStatusFieldName] ?? "") === status,
      ),
    }}));
  }}, [availableStatuses, records, currentStatusFieldName]);

  return (
    <Panel title={{title}} subtitle={{subtitle}}>
      <div className="toolbar">
        <input
          value={{query}}
          onChange={{(event) => onQueryChange(event.currentTarget.value)}}
          placeholder={{`Search ${{recordLabel.toLowerCase()}}`}}
        />
        {{currentStatusFieldName ? (
          <select
            value={{selectedStatus}}
            onChange={{(event) => onStatusChange(event.currentTarget.value)}}
          >
            <option value="">All statuses</option>
            {{availableStatuses.map((status) => (
              <option key={{status}} value={{status}}>
                {{status}}
              </option>
            ))}}
          </select>
        ) : null}}
        {{currentStatusFieldName ? (
          <div className="segmentedControl">
            <button
              type="button"
              className={{viewMode === "list" ? "active" : ""}}
              onClick={{() => onViewModeChange("list")}}
            >
              List
            </button>
            <button
              type="button"
              className={{viewMode === "board" ? "active" : ""}}
              onClick={{() => onViewModeChange("board")}}
            >
              Board
            </button>
          </div>
        ) : null}}
      </div>

      {{records.length === 0 ? (
        <div className="emptyState">
          <h3>No {{recordLabel.toLowerCase()}} yet</h3>
          <p>Create the first record to start using the approved workflow locally.</p>
        </div>
      ) : viewMode === "board" && currentStatusFieldName ? (
        <div className="boardGrid">
          {{groupedRecords.map((group) => (
            <section key={{group.status}} className="boardColumn">
              <header>
                <h3>{{group.status}}</h3>
                <span>{{group.records.length}}</span>
              </header>
              <div className="recordList">
                {{group.records.map((record) => (
                  <button
                    key={{record.id}}
                    type="button"
                    className="recordCard"
                    onClick={{() => onSelectRecord(record)}}
                  >
                    <strong>{{formatRecordValue(record[currentTitleFieldName] ?? record.id)}}</strong>
                    {{currentBooleanFieldName ? (
                      <span className="statusChip">
                        {{Boolean(record[currentBooleanFieldName]) ? "Complete" : "Open"}}
                      </span>
                    ) : null}}
                  </button>
                ))}}
              </div>
            </section>
          ))}}
        </div>
      ) : (
        <div className="recordList">
          {{records.map((record) => (
            <button
              key={{record.id}}
              type="button"
              className="recordCard"
              onClick={{() => onSelectRecord(record)}}
            >
              <div className="recordCardHeader">
                <strong>{{formatRecordValue(record[currentTitleFieldName] ?? record.id)}}</strong>
                {{currentStatusFieldName ? (
                  <span className="statusChip">
                    {{formatRecordValue(record[currentStatusFieldName] ?? "Active")}}
                  </span>
                ) : null}}
              </div>
              <dl className="recordMeta">
                {{editableFields
                  .filter((field) => field.name !== currentTitleFieldName)
                  .slice(0, 3)
                  .map((field) => (
                    <div key={{field.name}}>
                      <dt>{{field.label}}</dt>
                      <dd>{{formatRecordValue(record[field.name] ?? "")}}</dd>
                    </div>
                  ))}}
              </dl>
            </button>
          ))}}
        </div>
      )}}
    </Panel>
  );
}}

function {editor_component}({{
  title,
  subtitle,
  draft,
  editableFields: currentFields,
  isEditing,
  onChangeField,
  onSubmit,
  onDelete,
  onReset,
}}: EditorProps) {{
  return (
    <Panel title={{title}} subtitle={{subtitle}}>
      <form className="editorForm" onSubmit={{onSubmit}}>
        {{currentFields.map((field) => {{
          const isLongText = ["description", "details", "summary", "notes", "comment"].includes(
            field.name.toLowerCase(),
          );
          const currentValue = draft[field.name];

          if (field.type === "boolean") {{
            return (
              <label key={{field.name}} className="checkboxField">
                <input
                  type="checkbox"
                  checked={{Boolean(currentValue)}}
                  onChange={{(event) => onChangeField(field, event.currentTarget.checked)}}
                />
                <span>{{field.label}}</span>
              </label>
            );
          }}

          return (
            <label key={{field.name}} className="formField">
              <span>{{field.label}}</span>
              {{isLongText ? (
                <textarea
                  rows={{4}}
                  required={{field.required}}
                  value={{String(currentValue ?? "")}}
                  onChange={{(event) => onChangeField(field, event.currentTarget.value)}}
                />
              ) : (
                <input
                  type={{field.type === "number" ? "number" : "text"}}
                  required={{field.required}}
                  value={{field.type === "number" ? Number(currentValue ?? 0) : String(currentValue ?? "")}}
                  onChange={{(event) => onChangeField(field, event.currentTarget.value)}}
                />
              )}}
            </label>
          );
        }})}}

        <div className="editorActions">
          <button type="submit">{{isEditing ? `Save ${{recordLabel}}` : `Create ${{recordLabel}}`}}</button>
          <button type="button" className="secondaryButton" onClick={{onReset}}>
            New {{recordLabel}}
          </button>
          {{isEditing ? (
            <button type="button" className="dangerButton" onClick={{onDelete}}>
              Delete
            </button>
          ) : null}}
        </div>
      </form>
    </Panel>
  );
}}

export default function App() {{
  const [records, setRecords] = useState<ItemRecord[]>(() => readInitialRecords());
  const [query, setQuery] = useState("");
  const [selectedStatus, setSelectedStatus] = useState("");
  const [viewMode, setViewMode] = useState<"list" | "board">("list");
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ItemRecord>(() => createEmptyRecord());

  useEffect(() => {{
    window.localStorage.setItem(storageKey, JSON.stringify(records));
  }}, [records]);

  const filteredRecords = useMemo(() => {{
    return records.filter((record) => {{
      if (!matchesQuery(record, query)) {{
        return false;
      }}

      if (statusFieldName && selectedStatus) {{
        return formatRecordValue(record[statusFieldName] ?? "") === selectedStatus;
      }}

      return true;
    }});
  }}, [records, query, selectedStatus]);

  const completedCount = useMemo(() => {{
    if (!booleanFieldName) {{
      return 0;
    }}

    return records.filter((record) => Boolean(record[booleanFieldName])).length;
  }}, [records]);

  const stageCount = useMemo(() => {{
    if (!statusFieldName) {{
      return 1;
    }}

    return new Set(
      records.map((record) => formatRecordValue(record[statusFieldName] ?? "")),
    ).size;
  }}, [records]);

  function handleSelectRecord(record: ItemRecord) {{
    setSelectedRecordId(record.id);
    setDraft({{ ...record }});
  }}

  function handleChangeField(field: DataField, value: string | boolean) {{
    setDraft((current) => {{
      const nextValue =
        field.type === "boolean"
          ? value
          : field.type === "number"
            ? Number(value)
            : value;

      return {{
        ...current,
        [field.name]:
          field.type === "number" && Number.isNaN(nextValue)
            ? 0
            : (nextValue as string | number | boolean),
      }};
    }});
  }}

  function handleReset() {{
    setSelectedRecordId(null);
    setDraft(createEmptyRecord());
  }}

  function handleSubmit(event: FormEvent<HTMLFormElement>) {{
    event.preventDefault();

    setRecords((current) => {{
      const nextRecord = normalizeRecord(draft);
      const existingIndex = current.findIndex((record) => record.id === nextRecord.id);

      if (existingIndex === -1) {{
        return [nextRecord, ...current];
      }}

      const nextRecords = [...current];
      nextRecords[existingIndex] = nextRecord;
      return nextRecords;
    }});

    setSelectedRecordId(draft.id);
  }}

  function handleDelete() {{
    if (!selectedRecordId) {{
      return;
    }}

    setRecords((current) => current.filter((record) => record.id !== selectedRecordId));
    handleReset();
  }}

  return (
    <{app_shell_component}>
      <header className="hero">
        <div>
          <p className="eyebrow">{{recordLabel}} workspace</p>
          <h1>{{appName}}</h1>
          <p className="summary">{{summary}}</p>
        </div>
        <div className="heroActions">
          <button type="button" onClick={{handleReset}}>
            New {{recordLabel}}
          </button>
        </div>
      </header>

      <{overview_component}
        totalCount={{records.length}}
        visibleCount={{filteredRecords.length}}
        completedCount={{completedCount}}
        stageCount={{stageCount}}
      />

      <section className="workspaceGrid">
        <{workspace_component}
          title={workspace_title_json}
          subtitle={workspace_subtitle_json}
          records={{filteredRecords}}
          titleFieldName={{titleFieldName}}
          statusFieldName={{statusFieldName}}
          booleanFieldName={{booleanFieldName}}
          query={{query}}
          selectedStatus={{selectedStatus}}
          viewMode={{statusFieldName ? viewMode : "list"}}
          onQueryChange={{setQuery}}
          onStatusChange={{setSelectedStatus}}
          onViewModeChange={{setViewMode}}
          onSelectRecord={{handleSelectRecord}}
        />
        <{editor_component}
          title={editor_title_json}
          subtitle={editor_subtitle_json}
          draft={{draft}}
          editableFields={{editableFields}}
          isEditing={{Boolean(selectedRecordId)}}
          onChangeField={{handleChangeField}}
          onSubmit={{handleSubmit}}
          onDelete={{handleDelete}}
          onReset={{handleReset}}
        />
      </section>
    </{app_shell_component}>
  );
}}
""",
            ),
            GeneratedFile(
                path="src/styles.css",
                content="""* {
  box-sizing: border-box;
}

:root {
  color: #e2e8f0;
  background: #0f172a;
  font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.5;
}

body {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
  background:
    radial-gradient(circle at top, rgba(56, 189, 248, 0.16), transparent 28%),
    linear-gradient(180deg, #0f172a 0%, #111827 100%);
}

button,
input,
select,
textarea {
  font: inherit;
}

#root {
  min-height: 100vh;
}

.appShell {
  width: min(1240px, calc(100% - 32px));
  margin: 0 auto;
  padding: 28px 0 48px;
}

.hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  padding: 28px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 18px;
  background: rgba(15, 23, 42, 0.84);
}

.eyebrow {
  margin: 0 0 8px;
  color: #7dd3fc;
  font-size: 0.8rem;
  font-weight: 600;
  text-transform: uppercase;
}

.hero h1,
.panel h2,
.metricCard strong,
.emptyState h3,
.boardColumn h3 {
  margin: 0;
}

.summary {
  max-width: 64ch;
  margin: 12px 0 0;
  color: #cbd5e1;
}

button,
select,
input,
textarea {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.9);
  color: #e2e8f0;
}

button {
  cursor: pointer;
  transition: background 120ms ease, border-color 120ms ease;
}

button:hover,
select:hover,
input:hover,
textarea:hover {
  border-color: rgba(125, 211, 252, 0.38);
}

button:focus-visible,
select:focus-visible,
input:focus-visible,
textarea:focus-visible {
  outline: 2px solid rgba(56, 189, 248, 0.45);
  outline-offset: 1px;
}

.heroActions,
.editorActions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.heroActions button,
.editorActions button {
  padding: 10px 14px;
  background: #0ea5e9;
  color: #f8fafc;
  border-color: transparent;
}

.secondaryButton,
.segmentedControl button,
.recordCard,
.dangerButton {
  background: rgba(30, 41, 59, 0.88);
  color: #e2e8f0;
  border-color: rgba(148, 163, 184, 0.18);
}

.dangerButton {
  color: #fecaca;
}

.panel {
  margin-top: 20px;
  padding: 22px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.82);
  box-shadow: 0 18px 48px rgba(2, 6, 23, 0.26);
}

.panelHeader {
  margin-bottom: 16px;
}

.panelHeader p {
  margin: 6px 0 0;
  color: #94a3b8;
}

.metricGrid,
.recordList,
.editorForm {
  display: grid;
  gap: 12px;
}

.metricGrid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.metricCard {
  padding: 16px;
  border-radius: 14px;
  background: rgba(30, 41, 59, 0.7);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.metricCard span {
  display: block;
  color: #94a3b8;
  font-size: 0.9rem;
  margin-bottom: 8px;
}

.metricCard strong {
  font-size: 1.9rem;
  color: #f8fafc;
}

.workspaceGrid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}

.toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) repeat(2, auto);
  gap: 10px;
  margin-bottom: 16px;
}

.toolbar input,
.toolbar select,
.segmentedControl button,
.editorForm input,
.editorForm textarea {
  padding: 10px 12px;
}

.segmentedControl {
  display: inline-grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.segmentedControl .active {
  background: rgba(14, 165, 233, 0.18);
  border-color: rgba(14, 165, 233, 0.48);
}

.recordList {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.recordCard {
  width: 100%;
  text-align: left;
  padding: 14px;
  border-radius: 14px;
}

.recordCardHeader {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.recordMeta {
  display: grid;
  gap: 8px;
  margin: 0;
}

.recordMeta div {
  display: grid;
  gap: 2px;
}

.recordMeta dt {
  color: #94a3b8;
  font-size: 0.84rem;
}

.recordMeta dd {
  margin: 0;
  color: #e2e8f0;
}

.statusChip {
  display: inline-flex;
  align-items: center;
  padding: 4px 9px;
  border-radius: 999px;
  background: rgba(14, 165, 233, 0.16);
  color: #bae6fd;
  white-space: nowrap;
  font-size: 0.82rem;
}

.boardGrid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.boardColumn {
  min-height: 240px;
  padding: 12px;
  border-radius: 14px;
  background: rgba(30, 41, 59, 0.55);
  border: 1px solid rgba(148, 163, 184, 0.12);
}

.boardColumn header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.boardColumn header span {
  color: #94a3b8;
}

.boardColumn .recordList {
  grid-template-columns: 1fr;
}

.formField,
.checkboxField {
  display: grid;
  gap: 8px;
}

.formField span,
.checkboxField span {
  color: #cbd5e1;
  font-size: 0.92rem;
}

.checkboxField {
  grid-template-columns: auto 1fr;
  align-items: center;
}

.checkboxField input {
  width: 18px;
  height: 18px;
}

.emptyState {
  padding: 18px;
  border-radius: 14px;
  border: 1px dashed rgba(148, 163, 184, 0.22);
  color: #cbd5e1;
}

@media (max-width: 800px) {
  .metricGrid,
  .workspaceGrid,
  .toolbar {
    grid-template-columns: 1fr;
  }

  .hero {
    display: grid;
    gap: 16px;
  }
}
""",
            ),
        ]
    )


async def _log_message(
    log: AgentLogger | None,
    message: str,
) -> None:
    if log is not None:
        await log(message)


async def _run_structured_agent(
    *,
    agent_name: str,
    schema_name: str,
    messages: list[dict[str, str]],
    response_model: type[TModel],
    fallback_factory: Callable[[], TModel] | None,
    post_validate: Callable[[TModel], TModel] | None = None,
    log: AgentLogger | None = None,
) -> TModel:
    # Every structured agent shares the same contract: ask the model for strict
    # JSON, validate it with Pydantic, retry once, and then fall back if allowed.
    settings = get_llm_settings()

    def finalize_result(result: TModel) -> TModel:
        if post_validate is not None:
            return post_validate(result)

        return result

    if not settings.enabled:
        if fallback_factory is not None:
            await _log_message(
                log,
                f"{agent_name} LLM config missing. Using fallback output.",
            )
            return finalize_result(fallback_factory())

        raise RuntimeError(
            f"{agent_name} LLM config missing in apps/server/.env."
        )

    client = LLMClient(settings)
    last_error: Exception | None = None

    for attempt in range(1, 3):
        await _log_message(
            log,
            f"{agent_name} calling model {settings.model} (attempt {attempt}/2).",
        )

        try:
            payload = await client.generate_structured_output(
                messages=messages,
                schema_name=schema_name,
                response_model=response_model,
            )
            result = finalize_result(response_model.model_validate(payload))

            await _log_message(
                log,
                f"{agent_name} produced valid JSON with model {settings.model}.",
            )
            return result
        except (GeneratedAppValidationError, LLMClientError, ValidationError) as error:
            last_error = error
            await _log_message(
                log,
                f"{agent_name} LLM attempt {attempt} failed: {error}",
            )

    if fallback_factory is None:
        raise RuntimeError(
            f"{agent_name} failed after 2 attempts: {last_error or 'unknown error'}"
        )

    fallback_reason = str(last_error) if last_error is not None else "unknown error"
    await _log_message(
        log,
        f"{agent_name} falling back to local output after repeated LLM failures: {fallback_reason}",
    )
    return finalize_result(fallback_factory())


async def requirements_agent(
    prompt: str,
    log: AgentLogger | None = None,
) -> RequirementsSpec:
    return await _run_structured_agent(
        agent_name="Requirements Agent",
        schema_name="requirements_spec",
        messages=build_requirements_messages(prompt),
        response_model=RequirementsSpec,
        fallback_factory=lambda: _build_fallback_requirements_spec(prompt),
        log=log,
    )


async def architecture_agent(
    prompt: str,
    requirements: RequirementsSpec,
    log: AgentLogger | None = None,
) -> ArchitectureSpec:
    return await _run_structured_agent(
        agent_name="Architecture Agent",
        schema_name="architecture_spec",
        messages=build_architecture_messages(
            prompt=prompt,
            requirements=requirements,
        ),
        response_model=ArchitectureSpec,
        fallback_factory=lambda: _build_fallback_architecture_spec(prompt, requirements),
        log=log,
    )


async def code_generation_agent(
    prompt: str,
    requirements: RequirementsSpec,
    architecture: ArchitectureSpec,
    log: AgentLogger | None = None,
) -> list[GeneratedFile]:
    generated_app = await _run_structured_agent(
        agent_name="Code Generation Agent",
        schema_name="generated_app_spec",
        messages=build_code_generation_messages(
            prompt=prompt,
            requirements=requirements,
            architecture=architecture,
        ),
        response_model=GeneratedAppSpec,
        fallback_factory=lambda: _build_fallback_generated_app(
            prompt,
            requirements,
            architecture,
        ),
        post_validate=lambda app_spec: validate_generated_app_spec(
            app_spec,
            requirements=requirements,
            architecture=architecture,
        ),
        log=log,
    )

    return generated_app.files


async def debug_agent(
    *,
    prompt: str,
    requirements: RequirementsSpec,
    architecture: ArchitectureSpec,
    failure_type: str,
    failure_logs: list[str],
    log: AgentLogger | None = None,
) -> DebugAnalysisSpec:
    return await _run_structured_agent(
        agent_name="Debug Agent",
        schema_name="debug_analysis_spec",
        messages=build_debug_messages(
            prompt=prompt,
            requirements=requirements,
            architecture=architecture,
            failure_type=failure_type,
            failure_logs=failure_logs,
        ),
        response_model=DebugAnalysisSpec,
        fallback_factory=None,
        log=log,
    )


async def patch_agent(
    *,
    prompt: str,
    requirements: RequirementsSpec,
    architecture: ArchitectureSpec,
    previous_files: list[GeneratedFile],
    failure_type: str,
    failure_logs: list[str],
    debug_summary: str,
    log: AgentLogger | None = None,
) -> list[GeneratedFile]:
    generated_app = await _run_structured_agent(
        agent_name="Patch Agent",
        schema_name="patched_generated_app_spec",
        messages=build_patch_messages(
            prompt=prompt,
            requirements=requirements,
            architecture=architecture,
            previous_files=previous_files,
            failure_type=failure_type,
            failure_logs=failure_logs,
            debug_summary=debug_summary,
        ),
        response_model=GeneratedAppSpec,
        fallback_factory=None,
        post_validate=lambda app_spec: validate_generated_app_spec(
            app_spec,
            requirements=requirements,
            architecture=architecture,
        ),
        log=log,
    )

    return generated_app.files
