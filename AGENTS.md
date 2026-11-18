# Project Purpose
To manage a list of agent skills that I used for development

## Generating Skills
- create a folder of <skill-name> in kebab case in `./skills/`
- Follows typical SKILL.md convention.
- Generate reuseable script in `<skill-name>/scripts` if needed
- Generate `README.md` for generated skills if possible

## Test strategy
- Test scripts execution, test cases/data may be generated but not commit to git

## TODO management
- TODOs are managed with skill `list-sqlite` (scripts in `skills/list-sqlite/scripts`), stored in `.ai/lists.db` (git-ignored) in the list named `todo`.
- When agent finds a problem in code, add it with `lists.py add todo "<title>" --priority P? --location <file:line> --note "<detail>"`; view with `view.py todo`.
- `TODO.md` / skill `todo-tracking` are no longer used.
- All agents are allowed to modify the `todo` list.

## Git Rule
- Never override or discard changes by user.
- Never commit or push if not asked to.


