import { useProgram } from '../context/ProgramContext'
import { AlertCircle, RefreshCw } from 'lucide-react'
import useAnalysis from '../hooks/useAnalysis'
import { AnalysisSidebar, AnalysisTable } from '../components/analysis'

const Analysis = () => {
  const { selectedProgram } = useProgram()
  const {
    categories,
    activeCategory,
    setActiveCategory,
    data,
    loading,
    counts,
    pagination,
    handlePageChange,
    refresh,
  } = useAnalysis(selectedProgram)

  if (!selectedProgram) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
        <div className="flex items-center space-x-3">
          <AlertCircle className="text-yellow-600" size={24} />
          <div>
            <h3 className="font-semibold text-yellow-900">No Program Selected</h3>
            <p className="text-sm text-yellow-700 mt-1">
              Please select a program from the sidebar to view analysis.
            </p>
          </div>
        </div>
      </div>
    )
  }

  const activeConfig = categories[activeCategory]
  const activeData = data[activeCategory]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Security Analysis</h1>
          <p className="text-gray-600 mt-2">
            Vulnerability candidates for{' '}
            <span className="font-semibold text-primary-600">{selectedProgram.name}</span>
          </p>
        </div>
        <button
          onClick={refresh}
          className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
        >
          <RefreshCw size={16} />
          <span>Refresh</span>
        </button>
      </div>

      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-3">
          <AnalysisSidebar
            categories={categories}
            activeCategory={activeCategory}
            counts={counts}
            loading={loading}
            onCategoryChange={setActiveCategory}
          />
        </div>

        <div className="col-span-12 lg:col-span-9">
          <div className="mb-4">
            <h2 className="text-xl font-semibold text-gray-900">{activeConfig?.label}</h2>
            <p className="text-sm text-gray-500">{activeConfig?.description}</p>
            {activeData && (
              <p className="text-sm text-gray-600 mt-1">
                Total: <span className="font-medium">{activeData.total}</span> results
              </p>
            )}
          </div>

          <AnalysisTable
            category={activeCategory}
            data={activeData}
            loading={loading[activeCategory]}
            pagination={pagination}
            onPageChange={handlePageChange}
          />
        </div>
      </div>
    </div>
  )
}

export default Analysis
