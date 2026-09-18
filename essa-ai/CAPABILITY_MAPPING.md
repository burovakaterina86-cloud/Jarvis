# Capability Mapping: Claude Code → ChatGPT

| Upstream-механика | ChatGPT-адаптация | Правило |
|---|---|---|
| `SKILL.md` frontmatter triggers | Semantic router в Project Instructions/Core | Активировать по смыслу, не только точной фразе |
| Bash/curl/scripts | Code execution/Work/подключённый Plugin либо инструкция | Не утверждать, что команда запущена, если инструмента нет |
| Perplexity API | ChatGPT Web Search по умолчанию; Perplexity только при реально доступной интеграции | Источники и свежесть сохранить |
| Browser CLI | Work/Computer Use/Cloud Browser, если доступно | Иначе ограничиться анализом/инструкцией |
| Local files | Project files / uploads / Files | Не выдумывать содержимое |
| Claude subagents | Multi-step routing / Work / специализированные плагины | Сохранять разделение ответственности |
| Claude memory files | Project source files + Memory semantics ChatGPT | Не обещать автономную запись в скрытые файлы |
| Image CLI/API | ChatGPT Image Generation или подключённый media plugin | Результат, референсы и ограничения важнее названия сервиса |
| Scheduled cron | ChatGPT Automations, если пользователь просит расписание/мониторинг | Учитывать минимальную поддерживаемую частоту |

## Внешние ключи
AgentOS upstream содержит методы, требующие сторонних API (Perplexity, SocialData, Groq, HikerAPI, Telethon и др.). Пакет не содержит ключей. Никогда не просить публиковать секреты в Project Knowledge.
