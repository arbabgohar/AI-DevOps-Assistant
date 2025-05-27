import { useState } from 'react';
import axios from 'axios';

function App() {
  const [log, setLog] = useState('');
  const [recommendation, setRecommendation] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const analyzeLog = async () => {
    if (!log.trim()) {
      setError('Please enter a log to analyze');
      return;
    }

    setIsLoading(true);
    setError('');
    setRecommendation('');

    try {
      const response = await axios.post('http://127.0.0.1:8000/analyze-log', {
        log: log
      });

      setRecommendation(response.data.recommendation);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to analyze log. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold text-gray-800 mb-8">
          AI DevOps Dashboard
        </h1>

        <div className="bg-white rounded-lg shadow-lg p-6">
          <div className="mb-6">
            <label 
              htmlFor="log" 
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              System Log
            </label>
            <textarea
              id="log"
              rows="8"
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500"
              placeholder="Paste your system log here..."
              value={log}
              onChange={(e) => setLog(e.target.value)}
            />
          </div>

          <button
            onClick={analyzeLog}
            disabled={isLoading}
            className={`w-full py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 ${
              isLoading ? 'opacity-75 cursor-not-allowed' : ''
            }`}
          >
            {isLoading ? (
              <div className="flex items-center justify-center">
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white mr-2" />
                Analyzing...
              </div>
            ) : (
              'Analyze Log'
            )}
          </button>

          {error && (
            <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-md">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          {recommendation && (
            <div className="mt-6">
              <h2 className="text-lg font-medium text-gray-900 mb-2">
                AI Recommendation
              </h2>
              <div className="bg-gray-50 rounded-md p-4">
                <pre className="whitespace-pre-wrap text-sm text-gray-700">
                  {recommendation}
                </pre>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App; 