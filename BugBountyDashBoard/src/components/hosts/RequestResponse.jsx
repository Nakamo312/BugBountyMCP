import React from 'react'
import { X } from 'lucide-react'

const RequestResponse = ({ response, onClear }) => {
  if (!response) return null

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="font-semibold text-gray-900">Response</h4>
        <button onClick={onClear} className="text-gray-400 hover:text-gray-600">
          <X size={18} />
        </button>
      </div>

      {response.error ? (
        <div className="bg-red-50 border border-red-200 rounded p-3">
          <p className="text-sm text-red-800 font-medium">Error</p>
          <p className="text-sm text-red-600 mt-1">{response.error}</p>
          <p className="text-xs text-red-500 mt-2 font-mono">{response.url}</p>
        </div>
      ) : (
        <>
          <div className="flex items-center space-x-4 text-sm">
            <div>
              <span className="text-gray-600">Status: </span>
              <span
                className={`font-semibold ${
                  response.status >= 200 && response.status < 300
                    ? 'text-green-600'
                    : response.status >= 400
                    ? 'text-red-600'
                    : 'text-gray-600'
                }`}
              >
                {response.status} {response.statusText}
              </span>
            </div>
            <div>
              <span className="text-gray-600">URL: </span>
              <span className="font-mono text-xs text-gray-800">{response.url}</span>
            </div>
          </div>

          {response.headers && (
            <div>
              <h5 className="text-sm font-semibold text-gray-700 mb-2">Response Headers</h5>
              <div className="bg-gray-50 border border-gray-200 rounded p-3 space-y-1 max-h-32 overflow-y-auto">
                {Object.entries(response.headers).map(([key, value]) => (
                  <div key={key} className="flex items-start space-x-2 text-xs">
                    <span className="font-medium text-gray-700 min-w-[150px]">{key}:</span>
                    <span className="text-gray-600 font-mono break-all">{String(value)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div>
            <h5 className="text-sm font-semibold text-gray-700 mb-2">Response Body</h5>
            <div className="border border-gray-200 rounded overflow-hidden">
              <iframe
                srcDoc={`
                  <!DOCTYPE html>
                  <html>
                    <head>
                      <meta charset="utf-8">
                      <style>
                        body { margin: 0; padding: 16px; font-family: monospace; font-size: 12px; background: #fff; color: #000; }
                        pre { margin: 0; white-space: pre-wrap; word-wrap: break-word; }
                      </style>
                    </head>
                    <body>
                      <pre>${
                        typeof response.data === 'object'
                          ? JSON.stringify(response.data, null, 2)
                          : String(response.data || '')
                      }</pre>
                    </body>
                  </html>
                `}
                className="w-full h-64 border-0"
                title="Response Body"
              />
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default RequestResponse
