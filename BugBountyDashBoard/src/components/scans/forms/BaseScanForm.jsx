export default function BaseScanForm({
  onScan,
  loading,
  children,
  initialValues = {},
}) {
  const [form, setForm] = useState(initialValues)

  const update = (key, value) =>
    setForm(prev => ({ ...prev, [key]: value }))

  const submit = e => {
    e.preventDefault()
    onScan(form)
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {typeof children === 'function'
        ? children({ form, update })
        : children}

      <SubmitButton loading={loading}>
        Run Scan
      </SubmitButton>
    </form>
  )
}
