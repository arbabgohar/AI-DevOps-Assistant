import { useEffect, useMemo, useState } from 'react';

function App() {
  const apiBaseUrl = useMemo(
    () => import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000',
    []
  );
  const [logInput, setLogInput] = useState('');
  const [latestLog, setLatestLog] = useState('');
  const [mode, setMode] = useState('manual');
  const [recommendation, setRecommendation] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [health, setHealth] = useState(null);
  const [logSource, setLogSource] = useState(null);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/health`);
        const data = await response.json();
        if (response.ok) {
          setHealth(data.metrics);
        }
      } catch (err) {
        setHealth(null);
      }
    };

    const fetchLogSource = async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/log-source`);
        const data = await response.json();
        if (response.ok) {
          setLogSource(data);
        }
      } catch (err) {
        setLogSource(null);
      }
    };

    fetchHealth();
    fetchLogSource();
  }, [apiBaseUrl]);

  const handleLoadSample = () => {
    setLogInput(
      [
        '2026-02-10 10:14:03 ERROR api-gateway: upstream timeout after 30s',
        '2026-02-10 10:14:04 WARN  auth-service: token validation slow (p95=2.8s)',
        '2026-02-10 10:14:05 INFO  autoscaler: cpu=92% mem=78% scaling to 4 replicas',
        '2026-02-10 10:14:08 ERROR payments: db connection pool exhausted'
      ].join('\n')
    );
  };

  const handleRefreshLatest = async () => {
    setError('');
    try {
      const response = await fetch(`${apiBaseUrl}/latest-log`);
      const data = await response.json();
      if (response.ok) {
        setLatestLog(data.log || '');
      } else {
        setError(data.detail || 'Failed to fetch latest logs.');
      }
    } catch (err) {
      setError('Error connecting to backend.');
    }
  };

  const handleAnalyze = async () => {
    setLoading(true);
    setRecommendation('');
    setError('');

    try {
      const endpoint = mode === 'auto' ? '/analyze-latest' : '/analyze-log';
      const response = await fetch(`${apiBaseUrl}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: mode === 'auto' ? undefined : JSON.stringify({ log: logInput })
      });

      const data = await response.json();
      if (response.ok) {
        setRecommendation(data.recommendation);
      } else {
        setError(data.detail || 'AI failed to analyze the log.');
      }
    } catch (err) {
      setError('Error connecting to backend.');
    }

    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6 flex flex-col items-center justify-center space-y-6">
      <h1 className="text-3xl font-bold">🧠 AI DevOps Assistant</h1>
      
      <div className="w-full max-w-3xl space-y-6">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="bg-gray-800 border border-gray-700 rounded p-4">
            <h2 className="text-lg font-semibold mb-2">System Health</h2>
            {health ? (
              <div className="text-sm text-gray-200 space-y-1">
                <div>CPU: {health.cpu.usage_percent}%</div>
                <div>Memory: {health.memory.percent}%</div>
                <div>Disk: {health.disk.percent}%</div>
              </div>
            ) : (
              <div className="text-sm text-gray-400">Health data unavailable.</div>
            )}
          </div>
          <div className="bg-gray-800 border border-gray-700 rounded p-4">
            <h2 className="text-lg font-semibold mb-2">Log Source</h2>
            {logSource ? (
              <div className="text-sm text-gray-200 space-y-1">
                <div>Status: {logSource.status}</div>
                {logSource.source?.path && <div>Path: {logSource.source.path}</div>}
                {logSource.status === 'disabled' && (
                  <div className="text-gray-400">Set LOG_FILE_PATH to enable.</div>
                )}
              </div>
            ) : (
              <div className="text-sm text-gray-400">Log source unavailable.</div>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-3 items-center">
          <span className="text-sm text-gray-300">Mode:</span>
          <button
            type="button"
            onClick={() => setMode('manual')}
            className={`px-3 py-1 rounded border ${
              mode === 'manual'
                ? 'bg-blue-600 border-blue-500'
                : 'bg-gray-800 border-gray-700'
            }`}
          >
            Manual Paste
          </button>
          <button
            type="button"
            onClick={() => setMode('auto')}
            className={`px-3 py-1 rounded border ${
              mode === 'auto'
                ? 'bg-blue-600 border-blue-500'
                : 'bg-gray-800 border-gray-700'
            }`}
          >
            Auto Pull
          </button>
          {mode === 'manual' && (
            <button
              type="button"
              onClick={handleLoadSample}
              className="px-3 py-1 rounded border border-gray-700 bg-gray-800 hover:bg-gray-700"
            >
              Load Sample Logs
            </button>
          )}
          {mode === 'auto' && (
            <button
              type="button"
              onClick={handleRefreshLatest}
              className="px-3 py-1 rounded border border-gray-700 bg-gray-800 hover:bg-gray-700"
            >
              Pull Latest Logs
            </button>
          )}
        </div>

        <textarea
          className="w-full h-40 p-4 bg-gray-800 border border-gray-600 rounded focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          placeholder="Paste your system log here..."
          value={logInput}
          onChange={(e) => setLogInput(e.target.value)}
          disabled={mode === 'auto'}
        />

        {mode === 'auto' && (
          <div className="w-full p-4 bg-gray-800 border border-gray-700 rounded">
            <div className="text-sm text-gray-300 mb-2">Latest buffered logs:</div>
            <pre className="whitespace-pre-wrap text-xs text-gray-100 font-mono max-h-40 overflow-auto">
              {latestLog || 'No log data pulled yet.'}
            </pre>
          </div>
        )}

        <button
          onClick={handleAnalyze}
          className="w-full bg-blue-600 px-6 py-2 rounded text-white font-semibold hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          disabled={loading || (mode === 'manual' && !logInput.trim())}
        >
          {loading ? (
            <div className="flex items-center justify-center space-x-2">
              <div className="animate-spin h-5 w-5 border-2 border-white border-t-transparent rounded-full" />
              <span>Analyzing...</span>
            </div>
          ) : (
            mode === 'auto' ? 'Analyze Latest Logs' : 'Analyze Log'
          )}
        </button>

        {error && (
          <div className="w-full p-4 bg-red-900/50 border border-red-500 rounded">
            <p className="text-red-200">{error}</p>
          </div>
        )}

        {recommendation && (
          <div className="w-full p-4 bg-green-900/50 border border-green-500 rounded">
            <h2 className="text-xl font-semibold mb-2 text-green-200">AI Recommendation</h2>
            <pre className="whitespace-pre-wrap text-green-100 font-mono text-sm">
              {recommendation}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
