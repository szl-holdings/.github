// szl-dashboards/smoke-monitor.jsonnet
// SZL Holdings flagship observability dashboard — Grafana-compatible Jsonnet
// Inspired by Grafana Labs grafonnet pattern.
// Doctrine v11 LOCKED 749/14/163. SLSA L1 honest.
// Signed-off-by: Yachay <yachay@szlholdings.ai>
// Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>

local flagships = ['a11oy', 'sentra', 'amaru', 'rosie', 'killinchu'];

{
  title: 'SZL Holdings — Flagship Smoke Monitor',
  uid: 'szl-smoke-monitor-v1',
  schemaVersion: 36,
  panels: [
    {
      id: i + 1,
      title: 'Flagship: ' + flagships[i],
      type: 'stat',
      targets: [{
        expr: 'up{job="szl-flagship", flagship="' + flagships[i] + '"}',
        legendFormat: flagships[i],
      }],
      fieldConfig: { defaults: { thresholds: {
        mode: 'absolute',
        steps: [{ color: 'red', value: 0 }, { color: 'green', value: 1 }],
      }}},
    }
    for i in std.range(0, std.length(flagships) - 1)
  ],
  tags: ['szl', 'doctrine-v11', 'slsa-l1', 'smoke'],
}
