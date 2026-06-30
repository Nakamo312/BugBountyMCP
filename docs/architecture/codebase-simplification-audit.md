# Codebase Simplification Audit

Дата: 2026-06-29

Этот аудит фиксирует текущий технический долг не как список вкусовых претензий,
а как рабочий backlog для упрощения проекта. Синтаксически проект живой:
`compileall` по `src`, `services` и `playwright` проходил без ошибок. Но
архитектурно код слишком часто делает вид, что декомпозиция уже произошла,
хотя старые комбайны просто получили новые имена.

## Главный диагноз

Проект любит существительные: `Provider`, `Workflow`, `Resolver`, `Evaluator`,
`Recorder`, `Facade`, `StorePort`, `CommandPort`, `QueryPort`. Часть этих
сущностей не несет самостоятельной модели. Они передают вызовы дальше,
сохраняют старые интерфейсы или маскируют старый god-object.

Самый опасный паттерн: старая форма не удаляется, а заворачивается в новую.
Так появляются compatibility-фасады, fallback-и, monkey patches, старые
приватные wrapper-методы и fake-порты, которые указывают на один и тот же
объект.

## Приоритеты резки

1. Убрать `OrchestrationStore` как нормальную DI-зависимость.
   Providers должны отдавать конкретные scenario-owned stores, а не один фасад
   на все. Сам фасад допустим только как временный adapter для старого API.

2. Убрать compatibility fallback из `ActionService`.
   Если уже есть `commands`, `queries`, `results`, `approvals`, значит старый
   `store` больше не должен быть частью нормального пути.

3. Переписать analysis routes/service через registry.
   Сейчас дублирование handler/service-кода раздувает проект без предметной
   сложности.

4. Разрезать `canonicalize_endpoint`.
   Нужны входные структуры вроде `EndpointObservationInput`,
   `TransportInput`, `RequestShapeInput`, `ResponseShapeInput`,
   `FingerprintInput`, а не огромная функция с десятками optional-параметров.

5. Понизить graph scoring до experimental feature extraction.
   Weighted sums без backtest по approve/reject/outcome нельзя продавать как
   ранжирование. Хранить raw features, логировать решения, потом калибровать.

6. Разрезать `AgentTaskDetail.jsx`.
   Страница держит polling, detail loading, activity cursor, follow-up composer,
   review actions и render branches. Ранее отмеченный compile-дефект с
   отсутствующим импортом `Inbox` в текущем снимке уже не актуален; проблема
   остаётся в размере и смешении ролей страницы.

7. Пройтись по `except Exception`.
   В routes нужен централизованный exception mapping. В recorder/recovery нужны
   конкретные DB/domain conflicts. В scanner-ах нужны typed scan errors.

## Конкретные запахи

- `src/api/infrastructure/orchestration/store.py`: compatibility facade стал
  роутером на десятки методов. Это не завершенная декомпозиция.
- `src/api/application/services/action.py`: выглядит как mini-container внутри
  application layer.
- `src/api/application/services/action_catalog_resolver.py`: resolver делает
  lookup, normalization, budget resolve, max target validation, bind_profile и
  mutation metadata. Название врет.
- `src/api/application/services/action_envelope.py`: payload хранит options и
  как `options`, и как top-level поля. Это двойная форма одного состояния.
- `services/surface-engine/surface_engine/canonicalize.py`: большая входная
  форма всей подсистемы, плюс compatibility monkey patch.
- `playwright/playwright_scanner.py`: browser lifecycle, crawling, state
  exploration, artifact collection, URL decisions, error handling и result
  assembly живут в одном объекте.
- `BugBountyDashBoard/src/pages/AgentTaskDetail.jsx`: React-комбайн на страницу.
- `governance/review_gates_allowlist.json`: большой allowlist снижает силу
  review gates. Новые исключения должны быть редкостью, не нормой.

## Рабочее правило

Не добавлять новый слой, если он только переименовывает старый. Упрощение
засчитывается только тогда, когда уменьшается количество нормальных путей
вызова, удаляется fallback или исчезает compatibility API.
