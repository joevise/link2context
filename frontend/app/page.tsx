'use client'

import { useState, useMemo, useCallback } from 'react'
import { Link, Loader2, Copy, Download, Check, Github, Sparkles, FileText, FileImage, Settings, Wand2, X, CheckCircle2 } from 'lucide-react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const loadingStages = [
  'Fetching page...',
  'Downloading images...',
  'Detecting videos...',
  'Formatting Markdown...',
]

interface MediaInfo {
  images: Record<string, string>
  videos: Array<{
    url: string
    thumbnail?: string
    local_thumbnail?: string
  }>
}

interface ConvertResult {
  status: string
  title?: string
  markdown?: string
  markdown_with_images?: string
  strategy_used?: string
  media?: MediaInfo
  error?: string
}

interface OCRConfig {
  provider: string
  base_url: string
  api_key: string
  model: string
  prompt: string
}

interface OCRResult {
  success: boolean
  image_path: string
  text?: string
  error?: string
}

const DEFAULT_OCR_CONFIG: OCRConfig = {
  provider: 'openai',
  base_url: 'https://api.openai.com/v1',
  api_key: '',
  model: 'gpt-4o',
  prompt: '请识别这张图片中的所有文字内容。保持原有的格式和结构，如果有标题、列表、表格等，请用Markdown格式输出。如果图片中没有文字，请回复"[图片无文字内容]"。只输出识别的内容，不要添加额外说明。'
}

export default function Home() {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingStage, setLoadingStage] = useState(0)
  const [result, setResult] = useState<ConvertResult | null>(null)
  const [copied, setCopied] = useState(false)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [showPreview, setShowPreview] = useState(true)
  
  // OCR related states
  const [selectedImages, setSelectedImages] = useState<Set<string>>(new Set())
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrResults, setOcrResults] = useState<Record<string, string>>({})
  const [showSettings, setShowSettings] = useState(false)
  const [ocrConfig, setOcrConfig] = useState<OCRConfig>(() => {
    // Load from localStorage if available
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('ocrConfig')
      if (saved) {
        try {
          return { ...DEFAULT_OCR_CONFIG, ...JSON.parse(saved) }
        } catch {}
      }
    }
    return DEFAULT_OCR_CONFIG
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!url.trim()) return

    setLoading(true)
    setResult(null)
    setLoadingStage(0)
    setSelectedImages(new Set())
    setOcrResults({})

    const stageInterval = setInterval(() => {
      setLoadingStage((prev) => (prev + 1) % loadingStages.length)
    }, 1200)

    try {
      const response = await fetch(`${API_URL}/api/convert`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() }),
      })
      const data = await response.json()
      setResult(data)
    } catch (error) {
      setResult({
        status: 'error',
        error: 'Failed to connect to server. Please ensure the API is running.',
      })
    } finally {
      clearInterval(stageInterval)
      setLoading(false)
    }
  }

  const handleCopy = async () => {
    const content = getProcessedMarkdown()
    if (content) {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleDownloadMd = () => {
    const content = getProcessedMarkdown()
    if (content) {
      const blob = new Blob([content], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${result?.title || 'context'}.md`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }
  }

  const handleDownloadPdf = async () => {
    if (!result?.markdown_with_images) return
    
    setPdfLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/generate-pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          markdown: result.markdown_with_images,
          title: result.title || 'Document',
        }),
      })

      if (!response.ok) throw new Error('PDF generation failed')

      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${result.title || 'document'}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (error) {
      console.error('PDF download failed:', error)
      alert('PDF generation failed. Please try again.')
    } finally {
      setPdfLoading(false)
    }
  }

  const toggleImageSelection = useCallback((imagePath: string) => {
    setSelectedImages(prev => {
      const newSet = new Set(prev)
      if (newSet.has(imagePath)) {
        newSet.delete(imagePath)
      } else {
        newSet.add(imagePath)
      }
      return newSet
    })
  }, [])

  const handleOCR = async () => {
    if (selectedImages.size === 0 || !ocrConfig.api_key) {
      if (!ocrConfig.api_key) {
        setShowSettings(true)
        alert('请先配置API Key')
      }
      return
    }

    setOcrLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/ocr`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_paths: Array.from(selectedImages),
          config: ocrConfig,
        }),
      })

      const data = await response.json()
      
      if (data.status === 'success') {
        const newResults: Record<string, string> = { ...ocrResults }
        data.results.forEach((r: OCRResult) => {
          if (r.success && r.text) {
            newResults[r.image_path] = r.text
          }
        })
        setOcrResults(newResults)
        setSelectedImages(new Set()) // Clear selection after OCR
      } else {
        alert(`OCR failed: ${data.error}`)
      }
    } catch (error) {
      console.error('OCR failed:', error)
      alert('OCR recognition failed. Please check your API configuration.')
    } finally {
      setOcrLoading(false)
    }
  }

  const saveOcrConfig = (config: OCRConfig) => {
    setOcrConfig(config)
    if (typeof window !== 'undefined') {
      localStorage.setItem('ocrConfig', JSON.stringify(config))
    }
  }

  // Get processed markdown with OCR results replacing images
  const getProcessedMarkdown = useCallback(() => {
    if (!result?.markdown_with_images) return ''
    
    let content = result.markdown_with_images
    
    // Replace images with OCR results
    Object.entries(ocrResults).forEach(([imagePath, text]) => {
      const imageRegex = new RegExp(`!\\[[^\\]]*\\]\\(${imagePath.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\)`, 'g')
      content = content.replace(imageRegex, `\n${text}\n`)
    })
    
    return content
  }, [result?.markdown_with_images, ocrResults])

  // Extract all image paths from content
  const allImagePaths = useMemo(() => {
    if (!result?.markdown_with_images) return []
    const matches = result.markdown_with_images.matchAll(/!\[[^\]]*\]\(([^)]+)\)/g)
    return Array.from(matches).map(m => m[1]).filter(p => p.includes('/api/images/'))
  }, [result?.markdown_with_images])

  // Render content with selectable images
  const renderedContent = useMemo(() => {
    if (!result?.markdown_with_images) return null
    
    const content = result.markdown_with_images
    const lines = content.split('\n')
    const elements: JSX.Element[] = []
    
    lines.forEach((line, index) => {
      // Handle images
      const imgMatch = line.match(/!\[([^\]]*)\]\(([^)]+)\)/)
      if (imgMatch) {
        const alt = imgMatch[1]
        let src = imgMatch[2]
        const imagePath = src
        
        // Check if this image has OCR result
        if (ocrResults[imagePath]) {
          elements.push(
            <div key={index} className="my-4 p-4 bg-green-50 border border-green-200 rounded-lg">
              <div className="text-xs text-green-600 mb-2 font-medium">✓ AI识别结果</div>
              <div className="text-slate-700 whitespace-pre-wrap">{ocrResults[imagePath]}</div>
            </div>
          )
          return
        }
        
        if (src.startsWith('/api/images/')) {
          src = `${API_URL}${src}`
        }
        
        const isSelected = selectedImages.has(imagePath)
        
        elements.push(
          <div 
            key={index} 
            className={`my-4 relative group cursor-pointer transition-all ${isSelected ? 'ring-4 ring-blue-500 rounded-lg' : ''}`}
            onClick={() => toggleImageSelection(imagePath)}
          >
            <img 
              src={src} 
              alt={alt} 
              className="max-w-full h-auto rounded-lg shadow-md"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none'
              }}
            />
            {/* Hover overlay */}
            <div className={`absolute inset-0 rounded-lg transition-all ${isSelected ? 'bg-blue-500/20' : 'bg-black/0 group-hover:bg-black/10'}`}>
              <div className={`absolute top-2 right-2 w-6 h-6 rounded-full flex items-center justify-center transition-all ${isSelected ? 'bg-blue-500 text-white' : 'bg-white/80 text-slate-400 opacity-0 group-hover:opacity-100'}`}>
                {isSelected ? <Check className="w-4 h-4" /> : <div className="w-3 h-3 border-2 border-slate-400 rounded" />}
              </div>
            </div>
            {/* Selection hint */}
            {!isSelected && (
              <div className="absolute bottom-2 left-2 px-2 py-1 bg-black/60 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity">
                点击选中进行AI识别
              </div>
            )}
          </div>
        )
        return
      }
      
      // Handle headers
      if (line.startsWith('# ')) {
        elements.push(<h1 key={index} className="text-2xl font-bold mt-6 mb-4">{line.slice(2)}</h1>)
        return
      }
      if (line.startsWith('## ')) {
        elements.push(<h2 key={index} className="text-xl font-semibold mt-5 mb-3">{line.slice(3)}</h2>)
        return
      }
      if (line.startsWith('### ')) {
        elements.push(<h3 key={index} className="text-lg font-medium mt-4 mb-2">{line.slice(4)}</h3>)
        return
      }
      
      // Handle video links
      if (line.includes('🎬')) {
        const linkMatch = line.match(/\[([^\]]+)\]\(([^)]+)\)/)
        if (linkMatch) {
          elements.push(
            <div key={index} className="my-2 p-3 bg-slate-100 rounded-lg">
              <span className="mr-2">🎬</span>
              <a 
                href={linkMatch[2]} 
                target="_blank" 
                rel="noopener noreferrer"
                className="text-blue-600 hover:text-blue-800 underline"
              >
                {linkMatch[1]}
              </a>
            </div>
          )
          return
        }
      }
      
      if (line.trim() === '---') {
        elements.push(<hr key={index} className="my-6 border-slate-300" />)
        return
      }
      
      if (line.trim()) {
        elements.push(<p key={index} className="my-2 leading-relaxed">{line}</p>)
      } else {
        elements.push(<div key={index} className="h-2" />)
      }
    })
    
    return elements
  }, [result?.markdown_with_images, selectedImages, ocrResults, toggleImageSelection])

  return (
    <main className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="w-full px-6 py-4 flex items-center justify-between max-w-5xl mx-auto">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-black flex items-center justify-center">
            <Link className="w-4 h-4 text-white" />
          </div>
          <span className="text-xl font-semibold tracking-tight">Link2Context</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowSettings(true)}
            className="p-2 rounded-full hover:bg-slate-200 transition-colors"
            title="AI Settings"
          >
            <Settings className="w-5 h-5 text-slate-600" />
          </button>
          <a
            href="https://github.com/futur-x/link2context"
            target="_blank"
            rel="noopener noreferrer"
            className="p-2 rounded-full hover:bg-slate-200 transition-colors"
          >
            <Github className="w-5 h-5 text-slate-600" />
          </a>
        </div>
      </header>

      {/* Hero Section */}
      <div className="flex flex-col items-center justify-center px-6 pt-16 pb-8">
        <div className="flex items-center gap-2 mb-4">
          <Sparkles className="w-5 h-5 text-amber-500" />
          <span className="text-sm font-medium text-slate-500">AI-Ready Context with OCR</span>
        </div>
        <h1 className="text-5xl md:text-6xl font-bold tracking-tight text-center mb-4 bg-gradient-to-b from-slate-900 to-slate-600 bg-clip-text text-transparent">
          From Link to Context.
        </h1>
        <p className="text-lg text-slate-500 text-center max-w-md mb-12">
          Turn any webpage into clean Markdown. AI-powered image text recognition.
        </p>

        {/* Input Form */}
        <form onSubmit={handleSubmit} className="w-full max-w-2xl">
          <div className="relative flex items-center gap-3 p-2 bg-white rounded-2xl shadow-xl shadow-slate-200/50 border border-slate-200/80">
            <div className="flex-1 flex items-center">
              <Link className="w-5 h-5 text-slate-400 ml-4 mr-3 flex-shrink-0" />
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="Paste URL here..."
                className="w-full py-3 pr-4 bg-transparent outline-none text-slate-900 placeholder:text-slate-400"
                disabled={loading}
              />
            </div>
            <button
              type="submit"
              disabled={loading || !url.trim()}
              className="px-6 py-3 bg-black text-white font-medium rounded-xl hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2 flex-shrink-0"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span className="hidden sm:inline">{loadingStages[loadingStage]}</span>
                  <span className="sm:hidden">Loading...</span>
                </>
              ) : (
                'Generate Context'
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Result Section */}
      {result && (
        <div className="w-full max-w-4xl mx-auto px-6 py-8">
          {result.error ? (
            <div className="bg-red-50 border border-red-200 rounded-2xl p-6">
              <p className="text-red-600 font-medium">❌ {result.error}</p>
            </div>
          ) : (
            <div className="bg-white rounded-2xl shadow-xl shadow-slate-200/50 border border-slate-200/80 overflow-hidden">
              {/* Result Header */}
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between px-6 py-4 border-b border-slate-100 gap-4">
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-slate-900 truncate">
                    {result.title || 'Extracted Content'}
                  </h3>
                  <div className="flex items-center gap-3 text-sm text-slate-400">
                    <span>Strategy: {result.strategy_used || 'unknown'}</span>
                    {allImagePaths.length > 0 && (
                      <>
                        <span>•</span>
                        <span>{allImagePaths.length} images</span>
                      </>
                    )}
                    {Object.keys(ocrResults).length > 0 && (
                      <>
                        <span>•</span>
                        <span className="text-green-600">{Object.keys(ocrResults).length} recognized</span>
                      </>
                    )}
                  </div>
                </div>
                
                {/* View Toggle */}
                <div className="flex items-center gap-1 bg-slate-100 rounded-lg p-1">
                  <button
                    onClick={() => setShowPreview(true)}
                    className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                      showPreview ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    <FileImage className="w-4 h-4 inline mr-1" />
                    Preview
                  </button>
                  <button
                    onClick={() => setShowPreview(false)}
                    className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                      !showPreview ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    <FileText className="w-4 h-4 inline mr-1" />
                    Raw
                  </button>
                </div>
              </div>

              {/* Actions Bar */}
              <div className="flex flex-wrap items-center gap-2 px-6 py-3 bg-slate-50 border-b border-slate-100">
                <button
                  onClick={handleCopy}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-white rounded-lg transition-colors border border-transparent hover:border-slate-200"
                >
                  {copied ? (
                    <>
                      <Check className="w-4 h-4 text-green-500" />
                      Copied!
                    </>
                  ) : (
                    <>
                      <Copy className="w-4 h-4" />
                      Copy
                    </>
                  )}
                </button>
                <button
                  onClick={handleDownloadMd}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-white rounded-lg transition-colors border border-transparent hover:border-slate-200"
                >
                  <FileText className="w-4 h-4" />
                  Download .md
                </button>
                <button
                  onClick={handleDownloadPdf}
                  disabled={pdfLoading}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-white rounded-lg transition-colors border border-transparent hover:border-slate-200 disabled:opacity-50"
                >
                  {pdfLoading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Generating...
                    </>
                  ) : (
                    <>
                      <Download className="w-4 h-4" />
                      Download PDF
                    </>
                  )}
                </button>
                
                {/* AI Recognition Button */}
                <button
                  onClick={handleOCR}
                  disabled={ocrLoading || selectedImages.size === 0}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed ml-auto"
                >
                  {ocrLoading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      识别中...
                    </>
                  ) : (
                    <>
                      <Wand2 className="w-4 h-4" />
                      AI识别 {selectedImages.size > 0 && `(${selectedImages.size})`}
                    </>
                  )}
                </button>
              </div>

              {/* Selection hint */}
              {showPreview && allImagePaths.length > 0 && selectedImages.size === 0 && Object.keys(ocrResults).length === 0 && (
                <div className="px-6 py-2 bg-blue-50 text-blue-700 text-sm flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4" />
                  点击图片选中，然后点击"AI识别"按钮识别图片中的文字
                </div>
              )}

              {/* Content Area */}
              <div className="p-6 max-h-[700px] overflow-auto">
                {showPreview ? (
                  <div className="prose prose-slate max-w-none">
                    {renderedContent}
                  </div>
                ) : (
                  <pre className="markdown-output text-slate-700 bg-slate-50 p-4 rounded-lg whitespace-pre-wrap">
                    {getProcessedMarkdown()}
                  </pre>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Settings Modal */}
      {showSettings && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
              <h2 className="text-lg font-semibold">AI识别配置</h2>
              <button
                onClick={() => setShowSettings(false)}
                className="p-1 hover:bg-slate-100 rounded-full"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="p-6 space-y-4">
              {/* Provider */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Provider</label>
                <select
                  value={ocrConfig.provider}
                  onChange={(e) => {
                    const provider = e.target.value
                    let base_url = ocrConfig.base_url
                    let model = ocrConfig.model
                    
                    if (provider === 'openai') {
                      base_url = 'https://api.openai.com/v1'
                      model = 'gpt-4o'
                    } else if (provider === 'claude') {
                      base_url = 'https://api.anthropic.com/v1'
                      model = 'claude-3-5-sonnet-20241022'
                    }
                    
                    saveOcrConfig({ ...ocrConfig, provider, base_url, model })
                  }}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="openai">OpenAI</option>
                  <option value="claude">Claude</option>
                  <option value="custom">Custom (OpenAI Compatible)</option>
                </select>
              </div>

              {/* Base URL */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Base URL</label>
                <input
                  type="text"
                  value={ocrConfig.base_url}
                  onChange={(e) => saveOcrConfig({ ...ocrConfig, base_url: e.target.value })}
                  placeholder="https://api.openai.com/v1"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              {/* API Key */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">API Key</label>
                <input
                  type="password"
                  value={ocrConfig.api_key}
                  onChange={(e) => saveOcrConfig({ ...ocrConfig, api_key: e.target.value })}
                  placeholder="sk-..."
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              {/* Model */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Model</label>
                <input
                  type="text"
                  value={ocrConfig.model}
                  onChange={(e) => saveOcrConfig({ ...ocrConfig, model: e.target.value })}
                  placeholder="gpt-4o"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-xs text-slate-500 mt-1">
                  OpenAI: gpt-4o, gpt-4-turbo | Claude: claude-3-5-sonnet-20241022
                </p>
              </div>

              {/* Prompt */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">识别提示词</label>
                <textarea
                  value={ocrConfig.prompt}
                  onChange={(e) => saveOcrConfig({ ...ocrConfig, prompt: e.target.value })}
                  rows={4}
                  placeholder="请识别这张图片中的所有文字内容..."
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                />
              </div>
            </div>

            <div className="px-6 py-4 border-t border-slate-200 flex justify-end gap-3">
              <button
                onClick={() => saveOcrConfig(DEFAULT_OCR_CONFIG)}
                className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900"
              >
                恢复默认
              </button>
              <button
                onClick={() => setShowSettings(false)}
                className="px-4 py-2 text-sm font-medium text-white bg-black rounded-lg hover:bg-slate-800"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="w-full px-6 py-8 text-center text-sm text-slate-400">
        <p>Built for LLMs. Input Link, Get Context with AI-powered OCR.</p>
      </footer>
    </main>
  )
}
