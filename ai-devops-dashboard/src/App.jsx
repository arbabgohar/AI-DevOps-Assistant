import { useState } from 'react';

function App() {
  const [logInput, setLogInput] = useState('');
  const [recommendation, setRecommendation] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleAnalyze = async () => {
    setLoading(true);
    setRecommendation('');
    setError('');

    try {
      const response = await fetch('http://127.0.0.1:8000/analyze-log', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ log: logInput }),
      });

      const data = await response.json();
      if (response.ok) {
        setRecommendation(data.recommendation);
      } else {
        setError('AI failed to analyze the log.');
      }
    } catch (err) {
      setError('Error connecting to backend.');
    }

    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6 flex flex-col items-center justify-center space-y-6">
      <h1 className="text-3xl font-bold">🧠 AI DevOps Assistant</h1>
      
      <div className="w-full max-w-xl space-y-6">
        <textarea
          className="w-full h-40 p-4 bg-gray-800 border border-gray-600 rounded focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          placeholder="Paste your system log here..."
          value={logInput}
          onChange={(e) => setLogInput(e.target.value)}
        />

        <button
          onClick={handleAnalyze}
          className="w-full bg-blue-600 px-6 py-2 rounded text-white font-semibold hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          disabled={loading || !logInput.trim()}
        >
          {loading ? (
            <div className="flex items-center justify-center space-x-2">
              <div className="animate-spin h-5 w-5 border-2 border-white border-t-transparent rounded-full" />
              <span>Analyzing...</span>
            </div>
          ) : (
            'Analyze Log'
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
