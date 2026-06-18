import json

from app.models import ArchitectureSpec, GeneratedFile, RequirementsSpec


REQUIREMENTS_SYSTEM_PROMPT = """You are the Requirements Agent for Agentic OS.
Convert a natural language app request into product requirements for a small local prototype.

Current prototype constraints:
- The generated app is a React + TypeScript + Vite frontend.
- Keep the scope suitable for a local prototype with client-side state.
- Avoid inventing backends, databases, authentication, payments, or third-party integrations unless the prompt clearly requires them.
- When the request exceeds the current prototype scope, capture that limitation in the constraints field.

Return only valid JSON that matches the provided schema.
Do not include markdown, explanations, or code fences.
"""


ARCHITECTURE_SYSTEM_PROMPT = """You are the Architecture Agent for Agentic OS.
Design a frontend architecture for a small React + TypeScript + Vite prototype.

Current architecture constraints:
- Keep the design aligned with a local frontend-only app.
- Prefer simple, realistic components and data models.
- Use the requirements object as the source of truth.

Return only valid JSON that matches the provided schema.
Do not include markdown, explanations, or code fences.
"""


CODE_GENERATION_SYSTEM_PROMPT = """You are the Code Generation Agent for Agentic OS.
Generate a complete, runnable Vite + React + TypeScript client-only application.

Hard requirements:
- The supplied requirements and architecture have already been user-approved. Treat them as the implementation contract.
- Build only a frontend React app that runs in Vite.
- Do not generate backend code, API servers, databases, authentication systems, Docker files, shell scripts, or environment files.
- Keep the app client-only and use local browser state.
- Implement the requested product itself, not a notes app, prompt viewer, requirements viewer, architecture viewer, checklist, or meta dashboard unless that exact product was explicitly requested.
- Do not render the prompt, requirements, architecture, or feature list as the main UI instead of building the product workflow.
- Every approved feature should appear as concrete interactive UI behavior, local state, forms, views, filters, or derived data.
- Use the approved architecture component names as real React components or files whenever practical.
- Use the approved data models to drive the app state, inputs, collections, and visualizations.
- Return complete file contents, not patches, snippets, placeholders, or markdown fences.
- Keep the file set compact and practical for a local prototype.
- package.json must set private to true.
- package.json scripts must be exactly:
  - dev: "vite"
  - build: "vite build"
  - preview: "vite preview"
- Allowed top-level files: package.json, index.html, tsconfig.json, tsconfig.app.json, tsconfig.node.json, vite.config.ts, vite.config.js, vite.config.mjs, vite.config.mts, eslint.config.js, eslint.config.mjs, postcss.config.js, postcss.config.cjs, tailwind.config.js, tailwind.config.cjs, tailwind.config.ts
- Allowed directories: src/ and public/
- Required files: package.json, index.html, src/main.tsx

Return only valid JSON that matches the provided schema.
Do not include markdown, explanations, or code fences.
"""


DEBUG_SYSTEM_PROMPT = """You are the Debug Agent for Agentic OS.
Analyze why a frontend-only Vite + React + TypeScript app failed during local validation.

Focus on:
- install failures
- build failures
- preview startup failures
- runtime crashes
- timeouts

Use the failure logs as the primary source of truth.
Return only valid JSON that matches the provided schema.
Do not include markdown, explanations, or code fences.
"""


PATCH_SYSTEM_PROMPT = """You are the Patch Agent for Agentic OS.
Repair a generated frontend-only Vite + React + TypeScript app after a failed local validation attempt.

Hard requirements:
- Return the full replacement file list for the app as JSON.
- Keep the app frontend-only and compatible with a local Vite + React + TypeScript workflow.
- Do not add backend code, databases, Docker, shell scripts, environment files, or arbitrary commands.
- Keep package.json safe and compatible with the existing validation rules.
- Fix the failure using the provided logs and debug summary while preserving the requested product intent.
- Preserve the already approved requirements and architecture.
- Do not simplify the product into a prompt summary, note pad, checklist, or plan viewer.
- Keep approved features implemented as real UI behavior, not explanatory text.

Return only valid JSON that matches the provided schema.
Do not include markdown, explanations, or code fences.
"""


def build_requirements_messages(prompt: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": REQUIREMENTS_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": (
                "Create requirements for this app idea.\n\n"
                f"Prompt:\n{prompt}\n\n"
                "Output guidance:\n"
                '- "appName" should be short and product-like.\n'
                '- "summary" should be one or two sentences.\n'
                '- "features" should list concrete user-facing capabilities.\n'
                '- "constraints" should keep the prototype compatible with a local React + TypeScript + Vite app.\n'
            ),
        },
    ]


def build_architecture_messages(
    prompt: str,
    requirements: RequirementsSpec,
) -> list[dict[str, str]]:
    requirements_json = json.dumps(
        requirements.model_dump(),
        indent=2,
    )

    return [
        {
            "role": "system",
            "content": ARCHITECTURE_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": (
                "Design the frontend architecture for this app.\n\n"
                f"Original prompt:\n{prompt}\n\n"
                f"Requirements JSON:\n{requirements_json}\n\n"
                "Output guidance:\n"
                '- "stack" must describe the frontend, language, styling, build tool, and state management choices.\n'
                '- "components" should be practical UI pieces with one clear responsibility each.\n'
                '- "dataModels" should only include entities needed by the requirements.\n'
                "- Keep the architecture suitable for a local frontend-only prototype.\n"
            ),
        },
    ]


def build_code_generation_messages(
    prompt: str,
    requirements: RequirementsSpec,
    architecture: ArchitectureSpec,
) -> list[dict[str, str]]:
    requirements_json = json.dumps(
        requirements.model_dump(),
        indent=2,
    )
    architecture_json = json.dumps(
        architecture.model_dump(),
        indent=2,
    )

    return [
        {
            "role": "system",
            "content": CODE_GENERATION_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": (
                "Generate the full app source as JSON.\n\n"
                "This workflow is past human approval. The requirements and architecture below are already approved and must be implemented.\n\n"
                f"Original prompt:\n{prompt}\n\n"
                f"Requirements JSON:\n{requirements_json}\n\n"
                f"Architecture JSON:\n{architecture_json}\n\n"
                "Implementation guidance:\n"
                "- Build a polished but compact frontend-only React app.\n"
                "- Use TypeScript throughout the app.\n"
                "- Build the real product workflow described by the approved plan.\n"
                "- Convert approved features into screens, forms, lists, detail panels, filters, views, and local interactions.\n"
                "- Do not create a generic note-taking app or a UI that merely repeats the approved plan.\n"
                "- Include every file needed to install, build, and run the app locally with Vite.\n"
                "- Do not include lockfiles, node_modules, dist output, tests, server code, or shell scripts.\n"
                "- Keep the generated file list small and focused.\n"
            ),
        },
    ]


def build_debug_messages(
    *,
    prompt: str,
    requirements: RequirementsSpec,
    architecture: ArchitectureSpec,
    failure_type: str,
    failure_logs: list[str],
) -> list[dict[str, str]]:
    requirements_json = json.dumps(
        requirements.model_dump(),
        indent=2,
    )
    architecture_json = json.dumps(
        architecture.model_dump(),
        indent=2,
    )
    joined_logs = "\n".join(failure_logs[-120:])

    return [
        {
            "role": "system",
            "content": DEBUG_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": (
                "Analyze this generated app failure.\n\n"
                f"Original prompt:\n{prompt}\n\n"
                f"Failure type:\n{failure_type}\n\n"
                f"Requirements JSON:\n{requirements_json}\n\n"
                f"Architecture JSON:\n{architecture_json}\n\n"
                f"Failure logs:\n{joined_logs}\n\n"
                "Output guidance:\n"
                '- "summary" should be a concise human-readable diagnosis.\n'
                '- "rootCause" should identify the most likely direct cause.\n'
                '- "patchStrategy" should list practical fixes for the Patch Agent.\n'
            ),
        },
    ]


def build_patch_messages(
    *,
    prompt: str,
    requirements: RequirementsSpec,
    architecture: ArchitectureSpec,
    previous_files: list[GeneratedFile],
    failure_type: str,
    failure_logs: list[str],
    debug_summary: str,
) -> list[dict[str, str]]:
    requirements_json = json.dumps(
        requirements.model_dump(),
        indent=2,
    )
    architecture_json = json.dumps(
        architecture.model_dump(),
        indent=2,
    )
    files_json = json.dumps(
        [file.model_dump() for file in previous_files],
        indent=2,
    )
    joined_logs = "\n".join(failure_logs[-120:])

    return [
        {
            "role": "system",
            "content": PATCH_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": (
                "Repair this generated app and return the full replacement file list.\n\n"
                "The requirements and architecture below were already approved. Keep implementing that product while fixing the failure.\n\n"
                f"Original prompt:\n{prompt}\n\n"
                f"Failure type:\n{failure_type}\n\n"
                f"Debug summary:\n{debug_summary}\n\n"
                f"Requirements JSON:\n{requirements_json}\n\n"
                f"Architecture JSON:\n{architecture_json}\n\n"
                f"Previous files JSON:\n{files_json}\n\n"
                f"Failure logs:\n{joined_logs}\n\n"
                "Implementation guidance:\n"
                "- Fix the failure while keeping the app client-only.\n"
                "- Keep the approved product workflow intact.\n"
                "- Do not replace the app with a generic note pad, checklist, or plan summary.\n"
                "- Return a complete replacement file list for the project.\n"
                "- Only keep files needed for the app to install, build, and run locally.\n"
            ),
        },
    ]
