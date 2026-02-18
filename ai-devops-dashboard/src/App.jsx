import { useEffect, useCallback, useState } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
const HEALTH_POLL_INTERVAL_MS = 10_000;

function usageColor(percent) {
  if (percent >= 80) return 'text-red-400';
  if (percent >= 60) return 'text-yellow-400';
  return 'text-green-400';
}

function MetricRow({ label, value }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-gray-400">{label}</span>
      <span className={`font-mono font-semibold ${usageColor(value)}`}>{value}%</span>
    </div>
  );
}

function App() {
  const [logInput, setLogInput] = useState('');
  const [latestLog, setLatestLog] = useState('');
  const [mode, setMode] = useState('manual');
  const [recommendation, setRecommendation] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [health, setHealth] = useState(null);
  const [logSource, setLogSource] = useState(null);

  const fetchHealth = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/health`);
      if (response.ok) {
        const data = await response.json();
        setHealth(data.metrics);
      }
    } catch {
      setHealth(null);
    }
  }, []);

  const fetchLogSource = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/log-source`);
      if (response.ok) {
        const data = await response.json();
        setLogSource(data);
      }
    } catch {
      setLogSource(null);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    fetchLogSource();
    const interval = setInterval(fetchHealth, HEALTH_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchHealth, fetchLogSource]);

  const handleLoadSample = () => {
    setLogInput(
      [
        '2026-02-10 10:14:03 ERROR api-gateway: upstream timeout after 30s',
        '2026-02-10 10:14:04 WARN  auth-service: token validation slow (p95=2.8s)',
        '2026-02-10 10:14:05 INFO  autoscaler: cpu=92% mem=78% scaling to 4 replicas',
        '2026-02-10 10:14:08 ERROR payments: db connection pool exhausted',
      ].join('\n')
    );
  };

  const handleRefreshLatest = async () => {
    setError('');
    try {
      const response = await fetch(`${API_BASE_URL}/latest-log`);
      const data = await response.json();
      if (response.ok) {
        setLatestLog(data.log || '');
      } else {
        setError(data.detail || 'Failed to fetch latest logs.');
      }
    } catch {
      setError('Error connecting to backend.');
    }
  };

  const handleAnalyze = async () => {
    setLoading(true);
    setRecommendation('');
    setError('');

    try {
      const isAuto = mode === 'auto';
      const response = await fetch(`${API_BASE_URL}${isAuto ? '/analyze-latest' : '/analyze-log'}`, {
        method: 'POST',
        headers: isAuto ? undefined : { 'Content-Type': 'application/json' },
        body: isAuto ? undefined : JSON.stringify({ log: logInput }),
      });

      const data = await response.json();
      if (response.ok) {
        setRecommendation(data.recommendation);
      } else {
        setError(data.detail || 'AI failed to analyze the log.');
      }
    } catch {
      setError('Error connecting to backend.');
    }

    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6 flex flex-col items-center justify-center space-y-6">
      <div className="w-full max-w-3xl space-y-1">
        <h1 className="text-3xl font-bold text-center">AI DevOps Assistant</h1>
        <p className="text-center text-gray-400 text-sm">Powered by OpenAI · System metrics refresh every 10s</p>
      </div>

      <div className="w-full max-w-3xl space-y-6">
        {/* Status cards */}
        <div className="grid gap-4 md:grid-cols-2">
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 space-y-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">System Health</h2>
            {health ? (
              <div className="space-y-1.5">
                <MetricRow label="CPU" value={health.cpu.usage_percent} />
                <MetricRow label="Memory" value={health.memory.percent} />
                <MetricRow label="Disk" value={health.disk.percent} />
              </div>
            ) : (
              <p className="text-sm text-gray-500">Connecting to backend…</p>
            )}
          </div>

          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 space-y-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">Log Source</h2>
            {logSource ? (
              <div className="space-y-1 text-sm">
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-block w-2 h-2 rounded-full ${
                      logSource.status === 'enabled' ? 'bg-green-400' : 'bg-gray-500'
                    }`}
                  />
                  <span className="capitalize">{logSource.status}</span>
                </div>
                {logSource.source?.path && (
                  <p className="text-gray-400 truncate" title={logSource.source.path}>
                    {logSource.source.path}
                  </p>
                )}
                {logSource.source?.buffered_lines != null && (
                  <p className="text-gray-400">{logSource.source.buffered_lines} lines buffered</p>
                )}
                {logSource.status === 'disabled' && (
                  <p className="text-gray-500">Set LOG_FILE_PATH to enable auto mode.</p>
                )}
              </div>
            ) : (
              <p className="text-sm text-gray-500">Connecting to backend…</p>
            )}
          </div>
        </div>

        {/* Mode selector */}
        <div className="flex flex-wrap gap-3 items-center">
          <span className="text-sm text-gray-400">Mode:</span>
          <button
            type="button"
            onClick={() => setMode('manual')}
            className={`px-3 py-1 rounded border text-sm transition-colors ${
              mode === 'manual'
                ? 'bg-blue-600 border-blue-500 text-white'
                : 'bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700'
            }`}
          >
            Manual Paste
          </button>
          <button
            type="button"
            onClick={() => setMode('auto')}
            className={`px-3 py-1 rounded border text-sm transition-colors ${
              mode === 'auto'
                ? 'bg-blue-600 border-blue-500 text-white'
                : 'bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700'
            }`}
          >
            Auto Pull
          </button>

          {mode === 'manual' && (
            <button
              type="button"
              onClick={handleLoadSample}
              className="px-3 py-1 rounded border border-gray-700 bg-gray-800 text-gray-300 hover:bg-gray-700 text-sm transition-colors"
            >
              Load Sample Logs
            </button>
          )}
          {mode === 'auto' && (
            <button
              type="button"
              onClick={handleRefreshLatest}
              className="px-3 py-1 rounded border border-gray-700 bg-gray-800 text-gray-300 hover:bg-gray-700 text-sm transition-colors"
            >
              Pull Latest Logs
            </button>
          )}
        </div>

        {/* Log input / preview */}
        {mode === 'manual' ? (
          <textarea
            className="w-full h-40 p-4 bg-gray-800 border border-gray-600 rounded-lg font-mono text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none resize-y"
            placeholder="Paste your system log here…"
            value={logInput}
            onChange={(e) => setLogInput(e.target.value)}
          />
        ) : (
          <div className="w-full p-4 bg-gray-800 border border-gray-700 rounded-lg">
            <p className="text-xs text-gray-400 mb-2 uppercase tracking-wide">Latest buffered logs</p>
            <pre className="whitespace-pre-wrap text-xs text-gray-100 font-mono max-h-40 overflow-auto">
              {latestLog || 'No log data pulled yet. Click "Pull Latest Logs" above.'}
            </pre>
          </div>
        )}

        {/* Analyze button */}
        <button
          onClick={handleAnalyze}
          className="w-full bg-blue-600 px-6 py-2.5 rounded-lg text-white font-semibold hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          disabled={loading || (mode === 'manual' && !logInput.trim())}
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
              Analyzing…
            </span>
          ) : (
            mode === 'auto' ? 'Analyze Latest Logs' : 'Analyze Log'
          )}
        </button>

        {/* Error */}
        {error && (
          <div className="w-full p-4 bg-red-900/40 border border-red-500/60 rounded-lg">
            <p className="text-red-300 text-sm">{error}</p>
          </div>
        )}

        {/* AI recommendation */}
        {recommendation && (
          <div className="w-full p-4 bg-green-900/30 border border-green-500/60 rounded-lg space-y-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-green-400">AI Recommendation</h2>
            <pre className="whitespace-pre-wrap text-green-100 font-mono text-sm leading-relaxed">
              {recommendation}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
