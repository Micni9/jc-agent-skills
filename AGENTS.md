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
- When agent finds a problem in code, use skill `todo-tracking` with its scripts to add to `TODO.md`.
- All agents are allowed to modify `TODO.md`.

## Git Rule
- Never override or discard changes by user.
- Never commit or push if not asked to.


