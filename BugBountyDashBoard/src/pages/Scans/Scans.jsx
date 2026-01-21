import React, { useState } from 'react'
import { useProgram } from '../context/ProgramContext'
import {
  scanSubfinder, scanHTTPX, scanGAU, scanWaymore, scanKatana,
  scanPlaywright, scanLinkFinder, scanMantra, scanFFUF, scanDNSx,
  scanSubjack, scanASNMap, scanMapCIDR, scanNaabu
} from '../services/api'
import { 
  Play, Loader, CheckCircle, XCircle, AlertCircle,
  Search, Globe, FileCode, Bug, Shield, Network, Database
} from 'lucide-react'
import clsx from 'clsx'

const colorMap = {
  blue: { bg: 'bg-blue-100', text: 'text-blue-600' },
  green: { bg: 'bg-green-100', text: 'text-green-600' },
  purple: { bg: 'bg-purple-100', text: 'text-purple-600' },
  indigo: { bg: 'bg-indigo-100', text: 'text-indigo-600' },
  red: { bg: 'bg-red-100', text: 'text-red-600' },
  pink: { bg: 'bg-pink-100', text: 'text-pink-600' },
  yellow: { bg: 'bg-yellow-100', text: 'text-yellow-600' },
  orange: { bg: 'bg-orange-100', text: 'text-orange-600' },
  cyan: { bg: 'bg-cyan-100', text: 'text-cyan-600' },
  teal: { bg: 'bg-teal-100', text: 'text-teal-600' },
  rose: { bg: 'bg-rose-100', text: 'text-rose-600' },
  violet: { bg: 'bg-violet-100', text: 'text-violet-600' },
  slate: { bg: 'bg-slate-100', text: 'text-slate-600' },
  amber: { bg: 'bg-amber-100', text: 'text-amber-600' },
}

const Scans = () => {
  const { selectedProgram } = useProgram()
  const [activeScan, setActiveScan] = useState(null)
  const [scanResults, setScanResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const scanTypes = [
    {
      id: 'subfinder',
      name: 'Subfinder',
      description: 'Subdomain enumeration',
      icon: Search,
      color: 'blue',
      component: SubfinderScan,
      scanFunc: scanSubfinder,
    },
    {
      id: 'httpx',
      name: 'HTTPX',
      description: 'HTTP probing',
      icon: Globe,
      color: 'green',
      component: HTTPXScan,
      scanFunc: scanHTTPX,
    },
    {
      id: 'gau',
      name: 'GAU',
      description: 'URL discovery from web archives',
      icon: Database,
      color: 'purple',
      component: GAUScan,
      scanFunc: scanGAU,
    },
    {
      id: 'waymore',
      name: 'Waymore',
      description: 'URL discovery from multiple sources',
      icon: Search,
      color: 'indigo',
      component: WaymoreScan,
      scanFunc: scanWaymore,
    },
    {
      id: 'katana',
      name: 'Katana',
      description: 'Web crawling',
      icon: Network,
      color: 'red',
      component: KatanaScan,
      scanFunc: scanKatana,
    },
    {
      id: 'playwright',
      name: 'Playwright',
      description: 'Interactive browser-based crawling',
      icon: Globe,
      color: 'pink',
      component: PlaywrightScan,
      scanFunc: scanPlaywright,
    },
    {
      id: 'linkfinder',
      name: 'LinkFinder',
      description: 'JS analysis for hidden endpoints',
      icon: FileCode,
      color: 'yellow',
      component: LinkFinderScan,
      scanFunc: scanLinkFinder,
    },
    {
      id: 'mantra',
      name: 'Mantra',
      description: 'Secret scanning on JavaScript files',
      icon: Shield,
      color: 'orange',
      component: MantraScan,
      scanFunc: scanMantra,
    },
    {
      id: 'ffuf',
      name: 'FFUF',
      description: 'Directory/file fuzzing',
      icon: Bug,
      color: 'cyan',
      component: FFUFScan,
      scanFunc: scanFFUF,
    },
    {
      id: 'dnsx',
      name: 'DNSx',
      description: 'DNS enumeration',
      icon: Network,
      color: 'teal',
      component: DNSxScan,
      scanFunc: scanDNSx,
    },
    {
      id: 'subjack',
      name: 'Subjack',
      description: 'Subdomain takeover detection',
      icon: Shield,
      color: 'rose',
      component: SubjackScan,
      scanFunc: scanSubjack,
    },
    {
      id: 'asnmap',
      name: 'ASNMap',
      description: 'ASN/CIDR enumeration',
      icon: Network,
      color: 'violet',
      component: ASNMapScan,
      scanFunc: scanASNMap,
    },
    {
      id: 'mapcidr',
      name: 'MapCIDR',
      description: 'CIDR operations',
      icon: Database,
      color: 'slate',
      component: MapCIDRScan,
      scanFunc: scanMapCIDR,
    },
    {
      id: 'naabu',
      name: 'Naabu',
      description: 'Port scanning',
      icon: Network,
      color: 'amber',
      component: NaabuScan,
      scanFunc: scanNaabu,
    },
  ]

  const handleScan = async (scanType, formData) => {
    if (!selectedProgram) {
      setError('Please select a program first')
      return
    }

    setLoading(true)
    setError(null)
    setScanResults(null)
    setActiveScan(scanType.id)

    try {
      const response = await scanType.scanFunc({
        program_id: selectedProgram.id,
        ...formData,
      })
      setScanResults({
        status: response.data.status,
        message: response.data.message,
        results: response.data.results,
      })
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Scan failed')
      setScanResults({
        status: 'error',
        message: err.response?.data?.detail || err.message || 'Scan failed',
      })
    } finally {
      setLoading(false)
    }
  }

  if (!selectedProgram) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
        <div className="flex items-center space-x-3">
          <AlertCircle className="text-yellow-600" size={24} />
          <div>
            <h3 className="font-semibold text-yellow-900">No Program Selected</h3>
            <p className="text-sm text-yellow-700 mt-1">
              Please select a program from the sidebar to start scanning.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Scans</h1>
        <p className="text-gray-600 mt-2">
          Run various security scans for program: <span className="font-semibold text-primary-600">{selectedProgram.name}</span>
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex items-center space-x-2">
            <XCircle className="text-red-600" size={20} />
            <span className="text-red-900">{error}</span>
          </div>
        </div>
      )}

      {scanResults && (
        <div className={`rounded-lg p-4 ${
          scanResults.status === 'success' 
            ? 'bg-green-50 border border-green-200' 
            : 'bg-red-50 border border-red-200'
        }`}>
          <div className="flex items-start space-x-3">
            {scanResults.status === 'success' ? (
              <CheckCircle className="text-green-600 flex-shrink-0 mt-0.5" size={20} />
            ) : (
              <XCircle className="text-red-600 flex-shrink-0 mt-0.5" size={20} />
            )}
            <div className="flex-1">
              <p className={`font-medium ${
                scanResults.status === 'success' ? 'text-green-900' : 'text-red-900'
              }`}>
                {scanResults.message}
              </p>
              {scanResults.results && (
                <pre className="mt-2 text-xs text-gray-700 bg-white p-3 rounded overflow-x-auto">
                  {JSON.stringify(scanResults.results, null, 2)}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {scanTypes.map((scanType) => {
          const ScanComponent = scanType.component
          const Icon = scanType.icon
          const isActive = activeScan === scanType.id

          return (
            <div
              key={scanType.id}
              className={`bg-white rounded-lg shadow p-6 border-2 transition-colors ${
                isActive ? 'border-primary-500' : 'border-transparent hover:border-gray-200'
              }`}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center space-x-3">
                  <div className={clsx('p-2 rounded-lg', colorMap[scanType.color]?.bg || 'bg-gray-100')}>
                    <Icon className={clsx(colorMap[scanType.color]?.text || 'text-gray-600')} size={24} />
                  </div>
                  <div>
                    <h3 className="font-semibold text-gray-900">{scanType.name}</h3>
                    <p className="text-sm text-gray-600">{scanType.description}</p>
                  </div>
                </div>
              </div>

              <ScanComponent
                onScan={(formData) => handleScan(scanType, formData)}
                loading={loading && isActive}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}

// Scan Form Components
function SubfinderScan({ onScan, loading }) {
  const [targets, setTargets] = useState('')
  const [probe, setProbe] = useState(true)
  const [timeout, setTimeout] = useState(600)

  const handleSubmit = (e) => {
    e.preventDefault()
    onScan({
      targets: targets.split('\n').filter(t => t.trim()),
      probe,
      timeout: timeout || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Targets (one per line)</label>
        <textarea
          value={targets}
          onChange={(e) => setTargets(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          rows={3}
          required
        />
      </div>
      <div className="flex items-center space-x-2">
        <input
          type="checkbox"
          id="probe"
          checked={probe}
          onChange={(e) => setProbe(e.target.checked)}
          className="rounded"
        />
        <label htmlFor="probe" className="text-sm text-gray-700">Probe</label>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (seconds)</label>
        <input
          type="number"
          value={timeout}
          onChange={(e) => setTimeout(parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          min={1}
          max={3600}
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
      >
        {loading ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
        <span>Run Scan</span>
      </button>
    </form>
  )
}

function HTTPXScan({ onScan, loading }) {
  const [targets, setTargets] = useState('')
  const [timeout, setTimeout] = useState(600)

  const handleSubmit = (e) => {
    e.preventDefault()
    onScan({
      targets: targets.split('\n').filter(t => t.trim()),
      timeout: timeout || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Targets (URLs/domains, one per line)</label>
        <textarea
          value={targets}
          onChange={(e) => setTargets(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          rows={3}
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (seconds)</label>
        <input
          type="number"
          value={timeout}
          onChange={(e) => setTimeout(parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          min={1}
          max={3600}
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
      >
        {loading ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
        <span>Run Scan</span>
      </button>
    </form>
  )
}

function GAUScan({ onScan, loading }) {
  const [targets, setTargets] = useState('')
  const [includeSubs, setIncludeSubs] = useState(true)
  const [timeout, setTimeout] = useState(600)

  const handleSubmit = (e) => {
    e.preventDefault()
    onScan({
      targets: targets.split('\n').filter(t => t.trim()),
      include_subs: includeSubs,
      timeout: timeout || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Targets (domains, one per line)</label>
        <textarea
          value={targets}
          onChange={(e) => setTargets(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          rows={3}
          required
        />
      </div>
      <div className="flex items-center space-x-2">
        <input
          type="checkbox"
          id="includeSubs"
          checked={includeSubs}
          onChange={(e) => setIncludeSubs(e.target.checked)}
          className="rounded"
        />
        <label htmlFor="includeSubs" className="text-sm text-gray-700">Include Subdomains</label>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (seconds)</label>
        <input
          type="number"
          value={timeout}
          onChange={(e) => setTimeout(parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          min={1}
          max={3600}
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
      >
        {loading ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
        <span>Run Scan</span>
      </button>
    </form>
  )
}

function WaymoreScan({ onScan, loading }) {
  const [targets, setTargets] = useState('')
  const [timeout, setTimeout] = useState(600)

  const handleSubmit = (e) => {
    e.preventDefault()
    onScan({
      targets: targets.split('\n').filter(t => t.trim()),
      timeout: timeout || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Targets (domains, one per line)</label>
        <textarea
          value={targets}
          onChange={(e) => setTargets(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          rows={3}
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (seconds)</label>
        <input
          type="number"
          value={timeout}
          onChange={(e) => setTimeout(parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          min={1}
          max={3600}
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
      >
        {loading ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
        <span>Run Scan</span>
      </button>
    </form>
  )
}

function KatanaScan({ onScan, loading }) {
  const [targets, setTargets] = useState('')
  const [depth, setDepth] = useState(3)
  const [jsCrawl, setJsCrawl] = useState(true)
  const [headless, setHeadless] = useState(false)
  const [timeout, setTimeout] = useState(600)

  const handleSubmit = (e) => {
    e.preventDefault()
    onScan({
      targets: targets.split('\n').filter(t => t.trim()),
      depth,
      js_crawl: jsCrawl,
      headless,
      timeout: timeout || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Targets (URLs, one per line)</label>
        <textarea
          value={targets}
          onChange={(e) => setTargets(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          rows={3}
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Depth (1-10)</label>
        <input
          type="number"
          value={depth}
          onChange={(e) => setDepth(parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          min={1}
          max={10}
        />
      </div>
      <div className="flex items-center space-x-2">
        <input
          type="checkbox"
          id="jsCrawl"
          checked={jsCrawl}
          onChange={(e) => setJsCrawl(e.target.checked)}
          className="rounded"
        />
        <label htmlFor="jsCrawl" className="text-sm text-gray-700">JS Crawl</label>
      </div>
      <div className="flex items-center space-x-2">
        <input
          type="checkbox"
          id="headless"
          checked={headless}
          onChange={(e) => setHeadless(e.target.checked)}
          className="rounded"
        />
        <label htmlFor="headless" className="text-sm text-gray-700">Headless</label>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (seconds)</label>
        <input
          type="number"
          value={timeout}
          onChange={(e) => setTimeout(parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          min={1}
          max={3600}
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
      >
        {loading ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
        <span>Run Scan</span>
      </button>
    </form>
  )
}

function PlaywrightScan({ onScan, loading }) {
  const [targets, setTargets] = useState('')
  const [depth, setDepth] = useState(3)
  const [jsCrawl, setJsCrawl] = useState(true)
  const [headless, setHeadless] = useState(false)
  const [timeout, setTimeout] = useState(600)

  const handleSubmit = (e) => {
    e.preventDefault()
    onScan({
      targets: targets.split('\n').filter(t => t.trim()),
      depth,
      js_crawl: jsCrawl,
      headless,
      timeout: timeout || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Targets (URLs, one per line)</label>
        <textarea
          value={targets}
          onChange={(e) => setTargets(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          rows={3}
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Depth (1-10)</label>
        <input
          type="number"
          value={depth}
          onChange={(e) => setDepth(parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          min={1}
          max={10}
        />
      </div>
      <div className="flex items-center space-x-2">
        <input
          type="checkbox"
          id="jsCrawl"
          checked={jsCrawl}
          onChange={(e) => setJsCrawl(e.target.checked)}
          className="rounded"
        />
        <label htmlFor="jsCrawl" className="text-sm text-gray-700">JS Crawl</label>
      </div>
      <div className="flex items-center space-x-2">
        <input
          type="checkbox"
          id="headless"
          checked={headless}
          onChange={(e) => setHeadless(e.target.checked)}
          className="rounded"
        />
        <label htmlFor="headless" className="text-sm text-gray-700">Headless</label>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (seconds)</label>
        <input
          type="number"
          value={timeout}
          onChange={(e) => setTimeout(parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          min={1}
          max={3600}
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
      >
        {loading ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
        <span>Run Scan</span>
      </button>
    </form>
  )
}

function LinkFinderScan({ onScan, loading }) {
  const [targets, setTargets] = useState('')
  const [timeout, setTimeout] = useState(15)

  const handleSubmit = (e) => {
    e.preventDefault()
    onScan({
      targets: targets.split('\n').filter(t => t.trim()),
      timeout: timeout || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Targets (JS URLs, one per line)</label>
        <textarea
          value={targets}
          onChange={(e) => setTargets(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          rows={3}
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (seconds, 1-60)</label>
        <input
          type="number"
          value={timeout}
          onChange={(e) => setTimeout(parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          min={1}
          max={60}
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
      >
        {loading ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
        <span>Run Scan</span>
      </button>
    </form>
  )
}

function MantraScan({ onScan, loading }) {
  const [targets, setTargets] = useState('')
  const [timeout, setTimeout] = useState(300)

  const handleSubmit = (e) => {
    e.preventDefault()
    onScan({
      targets: targets.split('\n').filter(t => t.trim()),
      timeout: timeout || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Targets (JS URLs, one per line)</label>
        <textarea
          value={targets}
          onChange={(e) => setTargets(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          rows={3}
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (seconds)</label>
        <input
          type="number"
          value={timeout}
          onChange={(e) => setTimeout(parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          min={1}
          max={3600}
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
      >
        {loading ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
        <span>Run Scan</span>
      </button>
    </form>
  )
}

function FFUFScan({ onScan, loading }) {
  const [targets, setTargets] = useState('')
  const [timeout, setTimeout] = useState(600)

  const handleSubmit = (e) => {
    e.preventDefault()
    onScan({
      targets: targets.split('\n').filter(t => t.trim()),
      timeout: timeout || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Targets (URLs to fuzz, one per line)</label>
        <textarea
          value={targets}
          onChange={(e) => setTargets(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          rows={3}
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (seconds)</label>
        <input
          type="number"
          value={timeout}
          onChange={(e) => setTimeout(parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          min={1}
          max={3600}
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
      >
        {loading ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
        <span>Run Scan</span>
      </button>
    </form>
  )
}

function DNSxScan({ onScan, loading }) {
  const [targets, setTargets] = useState('')
  const [mode, setMode] = useState('basic')
  const [timeout, setTimeout] = useState(600)

  const handleSubmit = (e) => {
    e.preventDefault()
    onScan({
      targets: targets.split('\n').filter(t => t.trim()),
      mode,
      timeout: timeout || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Targets (domains/hosts/IPs, one per line)</label>
        <textarea
          value={targets}
          onChange={(e) => setTargets(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          rows={3}
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Mode</label>
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
        >
          <option value="basic">Basic</option>
          <option value="deep">Deep</option>
          <option value="ptr">PTR</option>
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (seconds)</label>
        <input
          type="number"
          value={timeout}
          onChange={(e) => setTimeout(parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          min={1}
          max={3600}
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
      >
        {loading ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
        <span>Run Scan</span>
      </button>
    </form>
  )
}

function SubjackScan({ onScan, loading }) {
  const [targets, setTargets] = useState('')
  const [timeout, setTimeout] = useState(300)

  const handleSubmit = (e) => {
    e.preventDefault()
    onScan({
      targets: targets.split('\n').filter(t => t.trim()),
      timeout: timeout || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Targets (domains, one per line)</label>
        <textarea
          value={targets}
          onChange={(e) => setTargets(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          rows={3}
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (seconds)</label>
        <input
          type="number"
          value={timeout}
          onChange={(e) => setTimeout(parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          min={1}
          max={3600}
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
      >
        {loading ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
        <span>Run Scan</span>
      </button>
    </form>
  )
}

function ASNMapScan({ onScan, loading }) {
  const [targets, setTargets] = useState('')
  const [mode, setMode] = useState('domain')
  const [timeout, setTimeout] = useState(300)

  const handleSubmit = (e) => {
    e.preventDefault()
    onScan({
      targets: targets.split('\n').filter(t => t.trim()),
      mode,
      timeout: timeout || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Targets (domains/ASNs/organizations, one per line)</label>
        <textarea
          value={targets}
          onChange={(e) => setTargets(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          rows={3}
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Mode</label>
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
        >
          <option value="domain">Domain</option>
          <option value="asn">ASN</option>
          <option value="organization">Organization</option>
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (seconds)</label>
        <input
          type="number"
          value={timeout}
          onChange={(e) => setTimeout(parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          min={1}
          max={3600}
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
      >
        {loading ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
        <span>Run Scan</span>
      </button>
    </form>
  )
}

function MapCIDRScan({ onScan, loading }) {
  const [cidrs, setCidrs] = useState('')
  const [operation, setOperation] = useState('expand')
  const [count, setCount] = useState('')
  const [hostCount, setHostCount] = useState('')
  const [skipBase, setSkipBase] = useState(false)
  const [skipBroadcast, setSkipBroadcast] = useState(false)
  const [shuffle, setShuffle] = useState(false)
  const [timeout, setTimeout] = useState(300)

  const handleSubmit = (e) => {
    e.preventDefault()
    onScan({
      cidrs: cidrs.split('\n').filter(c => c.trim()),
      operation,
      count: count ? parseInt(count) : null,
      host_count: hostCount ? parseInt(hostCount) : null,
      skip_base: skipBase,
      skip_broadcast: skipBroadcast,
      shuffle,
      timeout: timeout || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">CIDRs (one per line)</label>
        <textarea
          value={cidrs}
          onChange={(e) => setCidrs(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          rows={3}
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Operation</label>
        <select
          value={operation}
          onChange={(e) => setOperation(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
        >
          <option value="expand">Expand</option>
          <option value="slice_count">Slice Count</option>
          <option value="slice_host">Slice Host</option>
          <option value="aggregate">Aggregate</option>
        </select>
      </div>
      {operation === 'slice_count' && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Count (number of subnets)</label>
          <input
            type="number"
            value={count}
            onChange={(e) => setCount(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
            min={1}
          />
        </div>
      )}
      {operation === 'slice_host' && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Host Count (hosts per subnet)</label>
          <input
            type="number"
            value={hostCount}
            onChange={(e) => setHostCount(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
            min={1}
          />
        </div>
      )}
      <div className="flex items-center space-x-2">
        <input
          type="checkbox"
          id="skipBase"
          checked={skipBase}
          onChange={(e) => setSkipBase(e.target.checked)}
          className="rounded"
        />
        <label htmlFor="skipBase" className="text-sm text-gray-700">Skip Base IPs (.0)</label>
      </div>
      <div className="flex items-center space-x-2">
        <input
          type="checkbox"
          id="skipBroadcast"
          checked={skipBroadcast}
          onChange={(e) => setSkipBroadcast(e.target.checked)}
          className="rounded"
        />
        <label htmlFor="skipBroadcast" className="text-sm text-gray-700">Skip Broadcast IPs (.255)</label>
      </div>
      <div className="flex items-center space-x-2">
        <input
          type="checkbox"
          id="shuffle"
          checked={shuffle}
          onChange={(e) => setShuffle(e.target.checked)}
          className="rounded"
        />
        <label htmlFor="shuffle" className="text-sm text-gray-700">Shuffle IPs</label>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (seconds)</label>
        <input
          type="number"
          value={timeout}
          onChange={(e) => setTimeout(parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          min={1}
          max={3600}
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
      >
        {loading ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
        <span>Run Scan</span>
      </button>
    </form>
  )
}

function NaabuScan({ onScan, loading }) {
  const [targets, setTargets] = useState('')
  const [scanMode, setScanMode] = useState('active')
  const [ports, setPorts] = useState('')
  const [topPorts, setTopPorts] = useState('1000')
  const [rate, setRate] = useState(1000)
  const [scanType, setScanType] = useState('c')
  const [excludeCdn, setExcludeCdn] = useState(true)
  const [nmapCli, setNmapCli] = useState('nmap -sV')
  const [timeout, setTimeout] = useState(600)

  const handleSubmit = (e) => {
    e.preventDefault()
    onScan({
      targets: targets.split('\n').filter(t => t.trim()),
      scan_mode: scanMode,
      ports: ports || null,
      top_ports: topPorts,
      rate,
      scan_type: scanType,
      exclude_cdn: excludeCdn,
      nmap_cli: scanMode === 'nmap' ? nmapCli : null,
      timeout: timeout || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Targets (hosts/IPs, one per line)</label>
        <textarea
          value={targets}
          onChange={(e) => setTargets(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          rows={3}
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Scan Mode</label>
        <select
          value={scanMode}
          onChange={(e) => setScanMode(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
        >
          <option value="active">Active</option>
          <option value="passive">Passive</option>
          <option value="nmap">Nmap</option>
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Ports (optional, leave empty for top-ports)</label>
        <input
          type="text"
          value={ports}
          onChange={(e) => setPorts(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          placeholder="80,443,8080"
        />
      </div>
      {!ports && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Top Ports</label>
          <select
            value={topPorts}
            onChange={(e) => setTopPorts(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          >
            <option value="100">100</option>
            <option value="1000">1000</option>
            <option value="full">Full</option>
          </select>
        </div>
      )}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Rate (packets per second, 1-10000)</label>
        <input
          type="number"
          value={rate}
          onChange={(e) => setRate(parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          min={1}
          max={10000}
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Scan Type</label>
        <select
          value={scanType}
          onChange={(e) => setScanType(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
        >
          <option value="s">SYN (s)</option>
          <option value="c">CONNECT (c)</option>
        </select>
      </div>
      <div className="flex items-center space-x-2">
        <input
          type="checkbox"
          id="excludeCdn"
          checked={excludeCdn}
          onChange={(e) => setExcludeCdn(e.target.checked)}
          className="rounded"
        />
        <label htmlFor="excludeCdn" className="text-sm text-gray-700">Exclude CDN/WAF</label>
      </div>
      {scanMode === 'nmap' && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Nmap Command</label>
          <input
            type="text"
            value={nmapCli}
            onChange={(e) => setNmapCli(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
            placeholder="nmap -sV"
          />
        </div>
      )}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (seconds)</label>
        <input
          type="number"
          value={timeout}
          onChange={(e) => setTimeout(parseInt(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          min={1}
          max={3600}
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
      >
        {loading ? <Loader className="animate-spin" size={16} /> : <Play size={16} />}
        <span>Run Scan</span>
      </button>
    </form>
  )
}

export default Scans
