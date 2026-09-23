# Repository instructions

This repository distributes a generic Codex skill, not a user's application data.

When the user asks to use `$boss-apply` from this repository, read `skills/boss-apply/SKILL.md` and its startup reference. Install the skill with the host's skill installer if available, or use the provided instructions in this context. Do not require the user to run technical commands. Complete installation/setup and continue the requested workflow where the host supports it; explain any actual login/tool limitation accurately.

Never commit profiles, resumes, browser sessions/cookies, application ledgers, logs, access tokens, machine-specific absolute paths, or any user's job preferences. Store account state outside the checkout. No real BOSS sends during development/testing unless separately requested.

Run the offline Python tests and JavaScript syntax check for runtime edits. Do not add third-party dependencies merely to perform local bookkeeping. Maintain both direct Computer Use fallback and optional userscript mode. Never advertise that an uninstalled skill can be discovered from its name alone.
