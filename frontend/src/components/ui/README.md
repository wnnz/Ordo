# UI component layer

Shared page primitives live here. Pages should compose these components instead
of recreating headers, modal overlays, form labels, alerts, empty states,
filters, search fields, or status badges.

- `PageHeader` — page title, subtitle, and action slot
- `ModalShell` — accessible modal frame with optional form and footer
- `FormField` — label, hint, required marker, error, and control slot
- `AlertBanner` / `EmptyState` / `StatusBadge` — application feedback states
- `FilterDropdown` / `SearchInput` — list filtering controls
- `ChoiceCard` / `AvatarInitial` / `PanelSection` — shared choice, identity, and section layouts

Low-level Volt controls live in `src/volt`:

- `Button` — normal actions; variants, sizes, loading, disabled, active, and block layout
- `IconButton` — icon-only actions with required accessible label and matching interaction states
- `ActionCard` — card-shaped navigation and selection actions
- `ListButton` — menu and list-row actions with active and danger states
- `Select` — native strict-list mode by default, or an editable combobox using
  `editable`, `allowCustomValue`, `filterOptions`, `highlightMatches`, and
  `highlightFirstMatch`
- `InputText` and `Textarea` — text controls

Pages should use these controls rather than restyling native buttons or selects.
Native elements remain inside the control components and inside specialised
canvas widgets whose interaction model is not a normal application action.
Workflow-specific reusable editors live in `src/components/designer`.
`SystemSettingField` is the reusable administrator setting editor used by the
system settings page. Keep domain-specific components outside this directory
when their markup or state is not shared by multiple feature areas.
