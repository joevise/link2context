'use client'

import { useState, useMemo } from 'react'
import { Link, Loader2, Copy, Download, Check, Github, Sparkles, FileText, FileImage } from 'lucide-react'

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

export default function Home() {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingStage, setLoadingStage] = useState(0)
  const [result, setResult] = useState<ConvertResult | null>(null)
  const [copied, setCopied] = useState(false)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [showPreview, setShowPreview] = useState(true)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!url.trim()) return

    setLoading(true)
    setResult(null)
    setLoadingStage(0)

    // Cycle through loading stages
    const stageInterval = setInterval(() => {
      setLoadingStage((prev) => (prev + 1) % loadingStages.length)
    }, 1200)

    try {
      const response = await fetch(`${API_URL}/api/convert`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
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
    const content = showPreview ? result?.markdown_with_images : result?.markdown
    if (content) {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleDownloadMd = () => {
    if (result?.markdown) {
      const blob = new Blob([result.markdown], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${result.title || 'context'}.md`
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
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          markdown: result.markdown_with_images,
          title: result.title || 'Document',
        }),
      })

      if (!response.ok) {
        throw new Error('PDF generation failed')
      }

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

  // Render markdown with images
  const renderedContent = useMemo(() => {
    if (!result?.markdown_with_images) return null
    
    const content = result.markdown_with_images
    
    // Parse and render markdown with images
    const lines = content.split('\n')
    const elements: JSX.Element[] = []
    
    lines.forEach((line, index) => {
      // Handle images
      const imgMatch = line.match(/!\[([^\]]*)\]\(([^)]+)\)/)
      if (imgMatch) {
        const alt = imgMatch[1]
        let src = imgMatch[2]
        // Convert local path to full URL
        if (src.startsWith('/api/images/')) {
          src = `${API_URL}${src}`
        }
        elements.push(
          <div key={index} className="my-4">
            <img 
              src={src} 
              alt={alt} 
              className="max-w-full h-auto rounded-lg shadow-md"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none'
              }}
            />
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
      
      // Handle horizontal rules
      if (line.trim() === '---') {
        elements.push(<hr key={index} className="my-6 border-slate-300" />)
        return
      }
      
      // Regular paragraphs
      if (line.trim()) {
        elements.push(<p key={index} className="my-2 leading-relaxed">{line}</p>)
      } else {
        elements.push(<div key={index} className="h-2" />)
      }
    })
    
    return elements
  }, [result?.markdown_with_images])

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
        <a
          href="https://github.com"
          target="_blank"
          rel="noopener noreferrer"
          className="p-2 rounded-full hover:bg-slate-200 transition-colors"
        >
          <Github className="w-5 h-5 text-slate-600" />
        </a>
      </header>

      {/* Hero Section */}
      <div className="flex flex-col items-center justify-center px-6 pt-16 pb-8">
        <div className="flex items-center gap-2 mb-4">
          <Sparkles className="w-5 h-5 text-amber-500" />
          <span className="text-sm font-medium text-slate-500">AI-Ready Context with Images</span>
        </div>
        <h1 className="text-5xl md:text-6xl font-bold tracking-tight text-center mb-4 bg-gradient-to-b from-slate-900 to-slate-600 bg-clip-text text-transparent">
          From Link to Context.
        </h1>
        <p className="text-lg text-slate-500 text-center max-w-md mb-12">
          Turn any webpage into clean Markdown with images. Download as PDF or MD.
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
                    {result.media && (
                      <>
                        <span>•</span>
                        <span>{Object.keys(result.media.images).length} images</span>
                        {result.media.videos.length > 0 && (
                          <>
                            <span>•</span>
                            <span>{result.media.videos.length} videos</span>
                          </>
                        )}
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
              <div className="flex items-center gap-2 px-6 py-3 bg-slate-50 border-b border-slate-100">
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
                  className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-black hover:bg-slate-800 rounded-lg transition-colors disabled:opacity-50"
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
              </div>

              {/* Content Area */}
              <div className="p-6 max-h-[700px] overflow-auto">
                {showPreview ? (
                  <div className="prose prose-slate max-w-none">
                    {renderedContent}
                  </div>
                ) : (
                  <pre className="markdown-output text-slate-700 bg-slate-50 p-4 rounded-lg">
                    {result.markdown}
                  </pre>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <footer className="w-full px-6 py-8 text-center text-sm text-slate-400">
        <p>Built for LLMs. Input Link, Get Context with Images.</p>
      </footer>
    </main>
  )
}
