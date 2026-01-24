import { Loader } from 'lucide-react'

const colorClasses = {
  red: 'bg-red-100 text-red-800 border-red-200',
  orange: 'bg-orange-100 text-orange-800 border-orange-200',
  yellow: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  green: 'bg-green-100 text-green-800 border-green-200',
  blue: 'bg-blue-100 text-blue-800 border-blue-200',
  indigo: 'bg-indigo-100 text-indigo-800 border-indigo-200',
  purple: 'bg-purple-100 text-purple-800 border-purple-200',
  pink: 'bg-pink-100 text-pink-800 border-pink-200',
  cyan: 'bg-cyan-100 text-cyan-800 border-cyan-200',
  amber: 'bg-amber-100 text-amber-800 border-amber-200',
}

const activeColorClasses = {
  red: 'bg-red-500 text-white',
  orange: 'bg-orange-500 text-white',
  yellow: 'bg-yellow-500 text-white',
  green: 'bg-green-500 text-white',
  blue: 'bg-blue-500 text-white',
  indigo: 'bg-indigo-500 text-white',
  purple: 'bg-purple-500 text-white',
  pink: 'bg-pink-500 text-white',
  cyan: 'bg-cyan-500 text-white',
  amber: 'bg-amber-500 text-white',
}

const CategoryItem = ({ category, config, count, isActive, isLoading, onClick }) => {
  const baseClass = isActive
    ? activeColorClasses[config.color] || 'bg-gray-500 text-white'
    : 'bg-white hover:bg-gray-50 text-gray-900'

  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-3 rounded-lg border transition-all ${baseClass} ${
        isActive ? 'border-transparent shadow-md' : 'border-gray-200'
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex-1 min-w-0">
          <p className="font-medium text-sm truncate">{config.label}</p>
          <p className={`text-xs mt-0.5 truncate ${isActive ? 'opacity-80' : 'text-gray-500'}`}>
            {config.description}
          </p>
        </div>
        <div className="ml-2 flex-shrink-0">
          {isLoading ? (
            <Loader className="animate-spin" size={16} />
          ) : (
            <span
              className={`px-2 py-0.5 text-xs font-bold rounded-full ${
                isActive
                  ? 'bg-white/20'
                  : count > 0
                  ? colorClasses[config.color]
                  : 'bg-gray-100 text-gray-500'
              }`}
            >
              {count}
            </span>
          )}
        </div>
      </div>
    </button>
  )
}

const AnalysisSidebar = ({ categories, activeCategory, counts, loading, onCategoryChange }) => {
  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="font-semibold text-gray-900 mb-4">Categories</h3>
      <div className="space-y-2">
        {Object.entries(categories).map(([key, config]) => (
          <CategoryItem
            key={key}
            category={key}
            config={config}
            count={counts[key] || 0}
            isActive={activeCategory === key}
            isLoading={loading[key]}
            onClick={() => onCategoryChange(key)}
          />
        ))}
      </div>
    </div>
  )
}

export default AnalysisSidebar
