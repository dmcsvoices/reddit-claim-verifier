import { useState, useEffect } from 'react'
import './synthwave.css'

const API_BASE = 'http://localhost:5151'

type TabType = 'monitoring' | 'queues' | 'agents' | 'post'

function App() {
  const [activeTab, setActiveTab] = useState<TabType>('monitoring')
  const [health, setHealth] = useState<any>(null)
  const [posts, setPosts] = useState<any[]>([])
  const [subreddit, setSubreddit] = useState('')
  const [hours, setHours] = useState(4)
  const [scanning, setScanning] = useState(false)
  const [scanResult, setScanResult] = useState<any>(null)
  
  // Credentials state
  const [showCredentials, setShowCredentials] = useState(false)
  const [credentials, setCredentials] = useState({
    reddit_client_id: '',
    reddit_client_secret: '',
    reddit_username: '',
    reddit_password: '',
    reddit_user_agent: 'reddit-claim-verifier/1.0'
  })
  const [credentialsUpdating, setCredentialsUpdating] = useState(false)
  const [credentialsResult, setCredentialsResult] = useState<any>(null)
  
  // Queue Management state
  const [queueStatus, setQueueStatus] = useState<any>(null)
  const [queueStats, setQueueStats] = useState<any>(null)
  const [queueStates, setQueueStates] = useState<{[key: string]: boolean}>({})
  const [queueSettings, setQueueSettings] = useState<any>(null)
  const [pendingPostsModal, setPendingPostsModal] = useState<{visible: boolean, stage: string, posts: any[]}>({
    visible: false,
    stage: '',
    posts: []
  })
  const [expandedPosts, setExpandedPosts] = useState<{[key: number]: any}>({}) // Track expanded post data

  // Rejected posts state
  const [rejectedPostsModal, setRejectedPostsModal] = useState<{visible: boolean, posts: any[], selectedPost: any | null}>({
    visible: false,
    posts: [],
    selectedPost: null
  })

  // Fallback posts state
  const [fallbackStats, setFallbackStats] = useState<any>(null)
  const [fallbackPostsModal, setFallbackPostsModal] = useState<{visible: boolean, posts: any[], selectedPosts: number[], timeoutMinutes: number}>({
    visible: false,
    posts: [],
    selectedPosts: [],
    timeoutMinutes: 30
  })

  // Post tab state
  const [completedPosts, setCompletedPosts] = useState<any[]>([])
  const [postModal, setPostModal] = useState({
    visible: false,
    post: null,
    originalPost: '',
    editableResponse: '',
    suspended: false,
    posting: false
  })

  // Agent Backend state  
  const [availableModels, setAvailableModels] = useState<{[key: string]: string[]}>({}) 
  
  // Agent Management state
  const [agentPrompts, setAgentPrompts] = useState<any[]>([])
  const [agentConfig, setAgentConfig] = useState<any>(null)
  const [editingPrompt, setEditingPrompt] = useState<any>(null)
  const [testingEndpoint, setTestingEndpoint] = useState<string | null>(null)
  const [currentEndpoints, setCurrentEndpoints] = useState<{[key: string]: string}>({}) // Track current endpoint values per stage
  const [currentModels, setCurrentModels] = useState<{[key: string]: string}>({}) // Track current model selections per stage
  const [endpointTypes, setEndpointTypes] = useState<{[key: string]: string}>({}) // Track endpoint type per stage: 'together' or 'custom'

  // Posts filtering state
  const [stageFilter, setStageFilter] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<string>('all')

  // Database persistence helpers
  const saveAgentSettings = async () => {
    try {
      // Save each agent configuration to database
      const allStages = [...new Set([...Object.keys(currentEndpoints), ...Object.keys(endpointTypes)])]
      for (const stage of allStages) {
        if (currentModels[stage] && (endpointTypes[stage] === 'together' || currentEndpoints[stage])) {
          await fetch(`${API_BASE}/agents/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              agent_stage: stage,
              model: currentModels[stage],
              endpoint: endpointTypes[stage] === 'together' ? 'together-api' : currentEndpoints[stage],
              timeout: 120,
              max_concurrent: 2,
              endpoint_type: endpointTypes[stage] || 'custom',
              api_key_env: endpointTypes[stage] === 'together' ? 'TOGETHER_API_KEY' : null
            })
          })
        }
      }
      console.log('💾 Saved agent settings to database')
      
      // Reload queue manager to use new configurations
      try {
        const response = await fetch(`${API_BASE}/queue/reload-agents`, {
          method: 'POST'
        })
        if (response.ok) {
          console.log('🔄 Queue manager reloaded with new configurations')
        } else {
          console.warn('Failed to reload queue manager configurations')
        }
      } catch (error) {
        console.error('Failed to reload queue manager:', error)
      }
    } catch (error) {
      console.error('Failed to save agent settings to database:', error)
    }
  }

  const loadAgentSettings = async () => {
    try {
      const response = await fetch(`${API_BASE}/agents/config`)
      if (response.ok) {
        const data = await response.json()
        console.log('🔄 Loaded agent settings from database:', data)
        
        if (data.config) {
          const endpoints: {[key: string]: string} = {}
          const models: {[key: string]: string} = {}
          const endpointTypesData: {[key: string]: string} = {}

          for (const [stage, config] of Object.entries(data.config)) {
            const stageConfig = config as any
            endpoints[stage] = stageConfig.endpoint
            models[stage] = stageConfig.model
            // Map endpoint_type from database to frontend state
            endpointTypesData[stage] = stageConfig.endpoint_type || 'custom'
          }

          setCurrentEndpoints(endpoints)
          setCurrentModels(models)
          setEndpointTypes(endpointTypesData)
          console.log('🔄 Loaded endpoint types:', endpointTypesData)
          return data
        }
      }
    } catch (error) {
      console.error('Failed to load agent settings from database:', error)
    }
    return null
  }

  const checkHealth = async () => {
    try {
      const response = await fetch(`${API_BASE}/health`)
      const data = await response.json()
      setHealth(data)
    } catch (error: any) {
      setHealth({ status: 'error', error: error.message })
    }
  }

  const getPosts = async () => {
    try {
      const response = await fetch(`${API_BASE}/posts`)
      const data = await response.json()
      setPosts(data.posts)
    } catch (error) {
      console.error('Failed to get posts:', error)
    }
  }

  const insertDummy = async () => {
    try {
      await fetch(`${API_BASE}/dummy-insert`, { method: 'POST' })
      getPosts()
    } catch (error) {
      console.error('Failed to insert dummy:', error)
    }
  }

  const scanSubreddit = async () => {
    if (!subreddit.trim()) {
      alert('Please enter a subreddit name')
      return
    }

    setScanning(true)
    setScanResult(null)
    
    try {
      const response = await fetch(`${API_BASE}/scan`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          subreddit: subreddit.trim(),
          hours: hours
        })
      })
      
      const data = await response.json()
      
      if (!response.ok) {
        throw new Error(data.detail || 'Scan failed')
      }
      
      setScanResult(data)
      getPosts()
    } catch (error: any) {
      setScanResult({ error: error.message })
    } finally {
      setScanning(false)
    }
  }

  const updateCredentials = async () => {
    if (!credentials.reddit_client_id || !credentials.reddit_client_secret || 
        !credentials.reddit_username || !credentials.reddit_password) {
      alert('Please fill in all credential fields')
      return
    }

    setCredentialsUpdating(true)
    setCredentialsResult(null)
    
    try {
      const response = await fetch(`${API_BASE}/update-credentials`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(credentials)
      })
      
      const data = await response.json()
      
      if (!response.ok) {
        throw new Error(data.detail || 'Failed to update credentials')
      }
      
      setCredentialsResult(data)
      
      if (data.restart_required) {
        setCredentialsResult({ 
          ...data, 
          message: data.message + ' Please wait a moment for the backend to reload the new credentials...'
        })
        
        setTimeout(() => {
          checkHealth()
        }, 3000)
      }
      
    } catch (error: any) {
      setCredentialsResult({ error: error.message })
    } finally {
      setCredentialsUpdating(false)
    }
  }

  // Queue Management Functions
  const getQueueStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/queue/status`)
      const data = await response.json()
      setQueueStatus(data)
      
      // Extract queue states (paused/running) from the response
      if (data.queue_states) {
        setQueueStates(data.queue_states)
      }
    } catch (error) {
      console.error('Failed to get queue status:', error)
    }
  }

  const getQueueStats = async () => {
    try {
      const response = await fetch(`${API_BASE}/queue/stats`)
      const data = await response.json()
      setQueueStats(data)
    } catch (error) {
      console.error('Failed to get queue stats:', error)
    }
  }

  const getPendingPosts = async (stage: string) => {
    try {
      const response = await fetch(`${API_BASE}/queue/pending/${stage}`)
      const data = await response.json()
      setPendingPostsModal({
        visible: true,
        stage: stage,
        posts: data.pending_posts || []
      })
      // Clear expanded posts when opening new modal
      setExpandedPosts({})
    } catch (error) {
      console.error('Failed to get pending posts:', error)
    }
  }

  const getPostResults = async (postId: number) => {
    try {
      const response = await fetch(`${API_BASE}/queue/post-results/${postId}`)
      const data = await response.json()
      return data
    } catch (error) {
      console.error(`Failed to get post results for ${postId}:`, error)
      return null
    }
  }

  const getRejectedPosts = async () => {
    try {
      const response = await fetch(`${API_BASE}/queue/rejected`)
      const data = await response.json()
      setRejectedPostsModal(prev => ({
        ...prev,
        visible: true,
        posts: data.rejected_posts || [],
        selectedPost: null
      }))
    } catch (error) {
      console.error('Failed to get rejected posts:', error)
    }
  }

  const getFallbackStats = async () => {
    try {
      const response = await fetch(`${API_BASE}/queue/fallback/stats`)
      const data = await response.json()
      setFallbackStats(data)
    } catch (error) {
      console.error('Failed to get fallback stats:', error)
    }
  }

  const getFallbackPosts = async () => {
    try {
      const response = await fetch(`${API_BASE}/queue/fallback/posts`)
      const data = await response.json()
      setFallbackPostsModal(prev => ({
        ...prev,
        visible: true,
        posts: data.posts || [],
        selectedPosts: []
      }))
    } catch (error) {
      console.error('Failed to get fallback posts:', error)
    }
  }

  const retryFallbackPosts = async () => {
    try {
      const response = await fetch(`${API_BASE}/queue/fallback/retry`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          post_ids: fallbackPostsModal.selectedPosts,
          timeout_minutes: fallbackPostsModal.timeoutMinutes
        })
      })
      const data = await response.json()
      console.log('Retry scheduled:', data.message)

      // Close modal and refresh stats
      setFallbackPostsModal(prev => ({ ...prev, visible: false, selectedPosts: [] }))
      getFallbackStats()
      getQueueStats()
    } catch (error) {
      console.error('Failed to retry fallback posts:', error)
    }
  }

  const getPreviousStage = (currentStage: string): string | null => {
    const stageFlow = {
      'research': 'triage',
      'response': 'research',
      'editorial': 'response',
      'post_queue': 'editorial'
    }
    return stageFlow[currentStage as keyof typeof stageFlow] || null
  }

  // Function to format stage results content nicely
  const formatStageContent = (content: any): string => {
    if (typeof content === 'string') {
      return content
    }

    if (typeof content === 'object' && content !== null) {
      // Handle common agent response structures
      // For editorial agents, prioritize the 'result' field which contains the actual response content
      if (content.result) {
        return content.result
      }
      if (content.analysis) {
        return content.analysis
      }
      if (content.response) {
        return content.response
      }
      if (content.decision) {
        return `Decision: ${content.decision}\n\nReasoning: ${content.reasoning || 'No reasoning provided'}`
      }
      if (content.summary) {
        return content.summary
      }

      // Recursive function to format nested objects
      const formatObject = (obj: any, indent: string = ''): string => {
        if (typeof obj === 'string') {
          return obj
        }
        if (typeof obj === 'number' || typeof obj === 'boolean') {
          return String(obj)
        }
        if (Array.isArray(obj)) {
          return obj.map((item, index) => `${indent}${index + 1}. ${formatObject(item, indent + '  ')}`).join('\n')
        }
        if (typeof obj === 'object' && obj !== null) {
          return Object.entries(obj)
            .map(([key, value]) => {
              const formattedKey = key.charAt(0).toUpperCase() + key.slice(1).replace(/([A-Z])/g, ' $1')
              const formattedValue = formatObject(value, indent + '  ')
              return `${indent}${formattedKey}:\n${indent}  ${formattedValue}`
            })
            .join('\n\n')
        }
        return String(obj)
      }

      return formatObject(content)
    }

    return String(content)
  }

  // Function to fetch completed editorial posts
  const getCompletedPosts = async () => {
    try {
      const response = await fetch(`${API_BASE}/posts/completed-editorial`)
      const data = await response.json()
      setCompletedPosts(data.posts || [])
    } catch (error) {
      console.error('Error fetching completed posts:', error)
    }
  }

  // Function to handle opening post modal for review
  const handlePostReview = async (post: any) => {
    try {
      // Get the stage results for this post
      const response = await fetch(`${API_BASE}/queue/post-results/${post.id}`)
      const data = await response.json()

      // Try to get editorial result, fall back to response, then research, then triage
      const stageResults = data.stage_results || {}
      const editorialResult = stageResults.editorial || stageResults.response || stageResults.research || stageResults.triage

      setPostModal({
        visible: true,
        post: post,
        originalPost: `${post.title}\n\n${post.body || ''}`,
        editableResponse: editorialResult?.content ? formatStageContent(editorialResult.content) : 'No content available for editing',
        suspended: false,
        posting: false
      })
    } catch (error) {
      console.error('Error loading post details:', error)
    }
  }

  // Function to post to Reddit
  const postToReddit = async () => {
    if (!postModal.post) return

    setPostModal(prev => ({ ...prev, posting: true }))

    try {
      const response = await fetch(`${API_BASE}/posts/submit-to-reddit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          post_id: postModal.post.id,
          reddit_id: postModal.post.reddit_id,
          response_content: postModal.editableResponse
        })
      })

      const result = await response.json()

      if (response.ok) {
        alert('Successfully posted to Reddit!')
        setPostModal({ visible: false, post: null, originalPost: '', editableResponse: '', suspended: false, posting: false })
        getCompletedPosts() // Refresh the list
      } else {
        alert(`Error posting to Reddit: ${result.detail}`)
      }
    } catch (error) {
      console.error('Error posting to Reddit:', error)
      alert('Error posting to Reddit')
    } finally {
      setPostModal(prev => ({ ...prev, posting: false }))
    }
  }

  const handlePostClick = async (post: any) => {
    const postId = post.id

    // If already expanded, collapse it
    if (expandedPosts[postId]) {
      setExpandedPosts(prev => {
        const newState = { ...prev }
        delete newState[postId]
        return newState
      })
      return
    }

    // Fetch post results and expand
    const results = await getPostResults(postId)
    if (results) {
      setExpandedPosts(prev => ({
        ...prev,
        [postId]: results
      }))
    }
  }

  const getQueueSettings = async () => {
    try {
      const response = await fetch(`${API_BASE}/queue/settings`)
      const data = await response.json()
      setQueueSettings(data.settings || {})
    } catch (error) {
      console.error('Failed to get queue settings:', error)
    }
  }

  const pauseQueue = async (stage: string) => {
    try {
      const response = await fetch(`${API_BASE}/queue/pause/${stage}`, { method: 'POST' })
      if (response.ok) {
        // Update local state immediately for instant feedback
        setQueueStates(prev => ({ ...prev, [stage]: true }))
        // Also refresh full status
        getQueueStatus()
      }
    } catch (error) {
      console.error(`Failed to pause ${stage}:`, error)
    }
  }

  const resumeQueue = async (stage: string) => {
    try {
      const response = await fetch(`${API_BASE}/queue/resume/${stage}`, { method: 'POST' })
      if (response.ok) {
        // Update local state immediately for instant feedback
        setQueueStates(prev => ({ ...prev, [stage]: false }))
        // Also refresh full status
        getQueueStatus()
      }
    } catch (error) {
      console.error(`Failed to resume ${stage}:`, error)
    }
  }

  // Agent Management Functions
  const getAgentPrompts = async () => {
    try {
      const response = await fetch(`${API_BASE}/agents/prompts`)
      const data = await response.json()
      setAgentPrompts(data.prompts || [])
    } catch (error) {
      console.error('Failed to get agent prompts:', error)
    }
  }

  const getAgentConfig = async () => {
    try {
      const response = await fetch(`${API_BASE}/agents/config`)
      const data = await response.json()
      setAgentConfig(data)
      
      // Initialize currentEndpoints and models from database config
      if (data.config) {
        const initialEndpoints: {[key: string]: string} = {}
        const initialModels: {[key: string]: string} = {}
        
        Object.entries(data.config).forEach(([stage, config]: [string, any]) => {
          if (config.endpoint && config.model) {
            initialEndpoints[stage] = config.endpoint
            initialModels[stage] = config.model
            // Silently fetch models for each endpoint (no stage parameter = no loading indicator)
            testEndpointAndFetchModels(config.endpoint)
          }
        })
        
        // Only update if we don't have current settings loaded
        if (Object.keys(currentEndpoints).length === 0) {
          setCurrentEndpoints(initialEndpoints)
        }
        if (Object.keys(currentModels).length === 0) {
          setCurrentModels(initialModels)
        }
      }
    } catch (error) {
      console.error('Failed to get agent config:', error)
    }
  }

  const updateAgentPrompt = async (stage: string, prompt: string) => {
    try {
      const response = await fetch(`${API_BASE}/agents/prompts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent_stage: stage,
          system_prompt: prompt
        })
      })
      
      if (response.ok) {
        getAgentPrompts()
        setEditingPrompt(null)
      }
    } catch (error) {
      console.error('Failed to update agent prompt:', error)
    }
  }

  const refreshAgentData = async () => {
    try {
      console.log('🔄 Syncing agent data with latest defaults...')
      
      // First sync latest prompts from code to database
      const syncResponse = await fetch(`${API_BASE}/agents/prompts/sync`, {
        method: 'POST'
      })
      
      const syncData = await syncResponse.json()
      
      if (!syncResponse.ok) {
        throw new Error(syncData.detail || 'Sync failed')
      }
      
      console.log('✅ Sync successful:', syncData)
      
      // Then fetch the updated data to refresh UI
      await Promise.all([
        getAgentPrompts(),
        getAgentConfig()
      ])
      
      // Show user feedback about what was updated
      if (syncData.synced_agents.length > 0) {
        alert(`✅ Agent Data Refreshed!\n\nUpdated ${syncData.synced_agents.length}/${syncData.total_agents} agents with latest code changes.\n\nUpdated: ${syncData.synced_agents.map((a: any) => `${a.stage} (v${a.new_version})`).join(', ')}`)
      } else {
        // Still show success even if no updates needed
        console.log('📊 All agent data was already up-to-date')
      }
      
    } catch (error: any) {
      console.error('Failed to refresh agent data:', error)
      alert(`❌ Agent Data Refresh Failed:\n\n${error.message}`)
    }
  }

  // Agent Backend Functions (using backend proxy to avoid CORS)
  const testEndpointAndFetchModels = async (url: string, stage?: string) => {
    if (stage) setTestingEndpoint(stage)
    
    try {
      console.log(`Testing endpoint via backend proxy: ${url}`)
      
      // Normalize the URL by removing /v1 suffix for consistent caching
      const normalizedUrl = url.replace(/\/v1\/?$/, '')
      
      // Use our backend proxy to test the endpoint (bypasses CORS)
      const response = await fetch(`${API_BASE}/test-llm-endpoint`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          endpoint_url: normalizedUrl
        })
      })
      
      const data = await response.json()
      
      if (!response.ok) {
        throw new Error(data.detail || `HTTP ${response.status}: ${response.statusText}`)
      }
      
      console.log('Backend proxy response:', data)
      
      if (data.success && data.models) {
        const models = data.models
        // Use BOTH the original URL and normalized URL as cache keys to ensure dropdown finds models
        setAvailableModels(prev => ({ 
          ...prev, 
          [url]: models,           // Original URL as entered by user
          [normalizedUrl]: models  // Normalized URL for consistency
        }))
        console.log(`Cached models for keys: "${url}" and "${normalizedUrl}"`)
        console.log(`Found ${models.length} models:`, models)
        return { success: true, models, endpoint: data.endpoint }
      } else {
        throw new Error(data.error || 'Unknown error from backend proxy')
      }
    } catch (error: any) {
      console.error(`Error testing endpoint ${url}:`, error)
      return { success: false, error: error.message }
    } finally {
      if (stage) setTestingEndpoint(null)
    }
  }

  // Synthwave Theme Styles
  const synthwaveStyles = {
    app: {
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%)',
      color: '#ffffff',
      fontFamily: "'Orbitron', 'Courier New', monospace",
      fontSize: '14px'
    },
    header: {
      background: 'linear-gradient(90deg, #ff006e 0%, #8338ec 50%, #3a86ff 100%)',
      padding: '20px',
      borderBottom: '3px solid #ff006e',
      boxShadow: '0 0 20px rgba(255, 0, 110, 0.5)'
    },
    headerTitle: {
      margin: 0,
      fontSize: '2.5em',
      textShadow: '0 0 10px #ff006e',
      textAlign: 'center' as const,
      fontWeight: 900
    },
    nav: {
      background: 'rgba(255, 255, 255, 0.05)',
      padding: '15px',
      display: 'flex',
      justifyContent: 'center',
      gap: '20px',
      borderBottom: '1px solid rgba(255, 0, 110, 0.3)'
    },
    navButton: (active: boolean) => ({
      background: active ? 'linear-gradient(45deg, #ff006e, #8338ec)' : 'transparent',
      color: '#ffffff',
      border: active ? 'none' : '2px solid #ff006e',
      padding: '12px 24px',
      borderRadius: '25px',
      cursor: 'pointer',
      fontSize: '16px',
      fontWeight: 'bold',
      textTransform: 'uppercase' as const,
      transition: 'all 0.3s ease',
      boxShadow: active ? '0 0 15px rgba(255, 0, 110, 0.5)' : 'none'
    }),
    container: {
      padding: '30px',
      maxWidth: '1400px',
      margin: '0 auto'
    },
    card: {
      background: 'rgba(255, 255, 255, 0.05)',
      border: '1px solid rgba(131, 56, 236, 0.3)',
      borderRadius: '15px',
      padding: '25px',
      marginBottom: '25px',
      boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)',
      backdropFilter: 'blur(10px)'
    },
    cardTitle: {
      color: '#ff006e',
      fontSize: '1.5em',
      marginBottom: '20px',
      textShadow: '0 0 5px #ff006e',
      fontWeight: 700
    },
    button: {
      background: 'linear-gradient(45deg, #ff006e, #8338ec)',
      color: '#ffffff',
      border: 'none',
      padding: '10px 20px',
      borderRadius: '20px',
      cursor: 'pointer',
      fontSize: '14px',
      fontWeight: 'bold',
      transition: 'all 0.3s ease',
      boxShadow: '0 4px 15px rgba(255, 0, 110, 0.3)'
    },
    input: {
      background: 'rgba(255, 255, 255, 0.1)',
      border: '1px solid rgba(131, 56, 236, 0.5)',
      borderRadius: '10px',
      padding: '12px',
      color: '#ffffff',
      fontSize: '14px',
      width: '100%',
      marginBottom: '10px'
    },
    grid: {
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
      gap: '20px'
    }
  }

  useEffect(() => {
    // Load saved settings first, then fetch data
    const initializeData = async () => {
      await loadAgentSettings()
      checkHealth()
      getPosts()
      getAgentPrompts()
      getAgentConfig()
      getQueueStatus()
      getQueueStats()
      getQueueSettings()
      getFallbackStats()
    }
    initializeData()
  }, [])

  // Auto-save when settings change
  useEffect(() => {
    if (Object.keys(currentEndpoints).length > 0 || Object.keys(currentModels).length > 0 || Object.keys(endpointTypes).length > 0) {
      saveAgentSettings()
    }
  }, [currentEndpoints, currentModels, endpointTypes])

  return (
    <div style={synthwaveStyles.app} className="synthwave-bg">
      <header style={synthwaveStyles.header}>
        <h1 style={synthwaveStyles.headerTitle} className="glow-text">REDDIT CLAIM VERIFIER</h1>
        <div style={{ textAlign: 'center', marginTop: '10px', opacity: 0.8 }}>
          Advanced AI-Powered Content Analysis System
        </div>
      </header>
      
      <nav style={synthwaveStyles.nav}>
        <button 
          style={synthwaveStyles.navButton(activeTab === 'monitoring')}
          onClick={() => setActiveTab('monitoring')}
          className="synthwave-button"
        >
          📡 Monitoring
        </button>
        <button 
          style={synthwaveStyles.navButton(activeTab === 'queues')}
          onClick={() => {
            setActiveTab('queues')
            getQueueStatus()
            getQueueStats()
          }}
          className="synthwave-button"
        >
          🔄 Queue Control
        </button>
        <button
          style={synthwaveStyles.navButton(activeTab === 'post')}
          onClick={() => {
            setActiveTab('post')
            getCompletedPosts()
          }}
          className="synthwave-button"
        >
          📝 Post
        </button>
        <button
          style={synthwaveStyles.navButton(activeTab === 'agents')}
          onClick={() => {
            setActiveTab('agents')
            getAgentPrompts()
            getAgentConfig()
          }}
          className="synthwave-button"
        >
          ⚙️ Settings
        </button>
      </nav>
      
      <div style={synthwaveStyles.container}>
        {/* Health Status Bar */}
        <div style={{
          ...synthwaveStyles.card,
          marginBottom: '15px',
          padding: '15px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
            <span style={{ color: health?.status === 'healthy' ? '#00ff88' : '#ff3366' }}>
              {health?.status === 'healthy' ? '🟢 SYSTEM ONLINE' : '🔴 SYSTEM OFFLINE'}
            </span>
            {health?.total_posts && (
              <span style={{ color: '#8338ec' }}>
                📊 {health.total_posts} POSTS IN DATABASE
              </span>
            )}
          </div>
        </div>
        
        {/* Tab Content */}
        {activeTab === 'monitoring' && (
          <div>
            {/* Reddit Scanner Card */}
            <div style={synthwaveStyles.card} className="synthwave-card">
              <h2 style={synthwaveStyles.cardTitle}>📡 POST INGRESS MONITORING</h2>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '30px', marginBottom: '25px' }}>
                <div>
                  <h3 style={{ color: '#3a86ff', marginBottom: '15px' }}>Subreddit Scanner</h3>
                  <div style={{ marginBottom: '15px' }}>
                    <label style={{ display: 'block', marginBottom: '5px', color: '#ff006e' }}>Target Subreddit:</label>
                    <input
                      type="text"
                      placeholder="Enter subreddit name (e.g., Python)"
                      value={subreddit}
                      onChange={(e) => setSubreddit(e.target.value)}
                      style={synthwaveStyles.input}
                      className="synthwave-input"
                    />
                  </div>
                  
                  <div style={{ marginBottom: '20px' }}>
                    <label style={{ display: 'block', marginBottom: '5px', color: '#ff006e' }}>Time Window (hours):</label>
                    <input
                      type="number"
                      value={hours}
                      onChange={(e) => setHours(Number(e.target.value))}
                      min="1"
                      max="24"
                      style={{ ...synthwaveStyles.input, width: '120px' }}
                      className="synthwave-input"
                    />
                  </div>
                  
                  <button 
                    onClick={scanSubreddit} 
                    disabled={scanning}
                    style={{
                      ...synthwaveStyles.button,
                      background: scanning ? 'rgba(255, 255, 255, 0.1)' : 'linear-gradient(45deg, #00ff88, #3a86ff)',
                      cursor: scanning ? 'not-allowed' : 'pointer',
                      opacity: scanning ? 0.6 : 1
                    }}
                    className={scanning ? '' : 'synthwave-button'}
                  >
                    {scanning ? (
                      <>
                        <span className="loading-spinner" style={{marginRight: '8px'}}></span>
                        SCANNING...
                      </>
                    ) : (
                      '🚀 INITIATE SCAN'
                    )}
                  </button>
                </div>
                
                <div>
                  <h3 style={{ color: '#3a86ff', marginBottom: '15px' }}>Reddit API Configuration</h3>
                  <button 
                    onClick={() => setShowCredentials(!showCredentials)}
                    style={{
                      ...synthwaveStyles.button,
                      background: 'linear-gradient(45deg, #8338ec, #ff006e)',
                      marginBottom: '15px'
                    }}
                    className="synthwave-button"
                  >
                    {showCredentials ? '🔒 HIDE CREDENTIALS' : '🔑 CONFIGURE API'}
                  </button>
                  
                  {showCredentials && (
                    <div style={{
                      background: 'rgba(0, 0, 0, 0.3)',
                      padding: '20px',
                      borderRadius: '10px',
                      border: '1px solid rgba(255, 0, 110, 0.3)'
                    }}>
                      <div style={{ marginBottom: '15px' }}>
                        <label style={{ display: 'block', marginBottom: '5px', color: '#ff006e' }}>Client ID:</label>
                        <input
                          type="text"
                          value={credentials.reddit_client_id}
                          onChange={(e) => setCredentials({ ...credentials, reddit_client_id: e.target.value })}
                          placeholder="Reddit app client ID"
                          style={synthwaveStyles.input}
                          className="synthwave-input"
                        />
                      </div>
                      
                      <div style={{ marginBottom: '15px' }}>
                        <label style={{ display: 'block', marginBottom: '5px', color: '#ff006e' }}>Client Secret:</label>
                        <input
                          type="password"
                          value={credentials.reddit_client_secret}
                          onChange={(e) => setCredentials({ ...credentials, reddit_client_secret: e.target.value })}
                          placeholder="Reddit app client secret"
                          style={synthwaveStyles.input}
                          className="synthwave-input"
                        />
                      </div>
                      
                      <div style={{ marginBottom: '15px' }}>
                        <label style={{ display: 'block', marginBottom: '5px', color: '#ff006e' }}>Username:</label>
                        <input
                          type="text"
                          value={credentials.reddit_username}
                          onChange={(e) => setCredentials({ ...credentials, reddit_username: e.target.value })}
                          placeholder="Your Reddit username"
                          style={synthwaveStyles.input}
                          className="synthwave-input"
                        />
                      </div>
                      
                      <div style={{ marginBottom: '15px' }}>
                        <label style={{ display: 'block', marginBottom: '5px', color: '#ff006e' }}>Password:</label>
                        <input
                          type="password"
                          value={credentials.reddit_password}
                          onChange={(e) => setCredentials({ ...credentials, reddit_password: e.target.value })}
                          placeholder="Reddit password or app password"
                          style={synthwaveStyles.input}
                          className="synthwave-input"
                        />
                      </div>
                      
                      <div style={{ marginBottom: '20px' }}>
                        <label style={{ display: 'block', marginBottom: '5px', color: '#ff006e' }}>User Agent:</label>
                        <input
                          type="text"
                          value={credentials.reddit_user_agent}
                          onChange={(e) => setCredentials({ ...credentials, reddit_user_agent: e.target.value })}
                          style={synthwaveStyles.input}
                          className="synthwave-input"
                        />
                      </div>
                      
                      <button 
                        onClick={updateCredentials} 
                        disabled={credentialsUpdating}
                        style={{
                          ...synthwaveStyles.button,
                          background: credentialsUpdating ? 'rgba(255, 255, 255, 0.1)' : 'linear-gradient(45deg, #00ff88, #8338ec)'
                        }}
                        className={credentialsUpdating ? '' : 'synthwave-button'}
                      >
                        {credentialsUpdating ? (
                          <>
                            <span className="loading-spinner" style={{marginRight: '8px'}}></span>
                            UPDATING...
                          </>
                        ) : (
                          '💾 SAVE & RESTART'
                        )}
                      </button>
                      
                      {credentialsResult && (
                        <div style={{
                          marginTop: '15px',
                          padding: '10px',
                          borderRadius: '8px',
                          background: credentialsResult.error ? 'rgba(255, 51, 102, 0.2)' : 'rgba(0, 255, 136, 0.2)',
                          border: `1px solid ${credentialsResult.error ? '#ff3366' : '#00ff88'}`
                        }}>
                          <span style={{ color: credentialsResult.error ? '#ff3366' : '#00ff88' }}>
                            {credentialsResult.error ? '❌ ' + credentialsResult.error : '✅ ' + credentialsResult.message}
                          </span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
              
              {/* Scan Results */}
              {scanResult && (
                <div style={{
                  marginTop: '25px',
                  padding: '20px',
                  borderRadius: '10px',
                  background: scanResult.error ? 'rgba(255, 51, 102, 0.1)' : 'rgba(0, 255, 136, 0.1)',
                  border: `2px solid ${scanResult.error ? '#ff3366' : '#00ff88'}`
                }}>
                  {scanResult.error ? (
                    <div>
                      <h3 style={{ color: '#ff3366' }}>❌ SCAN FAILED</h3>
                      <p style={{ color: '#ff3366' }}>{scanResult.error}</p>
                    </div>
                  ) : (
                    <div>
                      <h3 style={{ color: '#00ff88' }}>✅ SCAN COMPLETED</h3>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px', marginBottom: '20px' }}>
                        <div style={{ textAlign: 'center' }}>
                          <div style={{ fontSize: '2em', color: '#3a86ff' }}>{scanResult.found}</div>
                          <div>Posts Found</div>
                        </div>
                        <div style={{ textAlign: 'center' }}>
                          <div style={{ fontSize: '2em', color: '#8338ec' }}>{scanResult.saved}</div>
                          <div>New Posts Saved</div>
                        </div>
                        <div style={{ textAlign: 'center' }}>
                          <div style={{ fontSize: '2em', color: '#ff006e' }}>r/{scanResult.subreddit}</div>
                          <div>Target Subreddit</div>
                        </div>
                        <div style={{ textAlign: 'center' }}>
                          <div style={{ fontSize: '2em', color: '#00ff88' }}>{scanResult.hours}h</div>
                          <div>Time Window</div>
                        </div>
                      </div>
                      
                      {scanResult.sample && scanResult.sample.length > 0 && (
                        <div>
                          <h4 style={{ color: '#8338ec', marginBottom: '15px' }}>Sample Posts Discovered:</h4>
                          {scanResult.sample.map((post: any, index: number) => (
                            <div key={index} style={{
                              background: 'rgba(131, 56, 236, 0.1)',
                              border: '1px solid rgba(131, 56, 236, 0.3)',
                              borderRadius: '8px',
                              padding: '15px',
                              marginBottom: '10px'
                            }}>
                              <h5 style={{ color: '#ffffff', margin: '0 0 5px 0' }}>{post.title}</h5>
                              <p style={{ color: '#8338ec', margin: '5px 0', fontSize: '0.9em' }}>
                                by u/{post.author} • {new Date(post.created_utc).toLocaleString()}
                              </p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
            
            {/* Recent Posts Card */}
            <div style={synthwaveStyles.card} className="synthwave-card">
              <h2 style={synthwaveStyles.cardTitle}>📋 RECENT POSTS DATABASE</h2>
              <div style={{ display: 'flex', gap: '15px', marginBottom: '20px', alignItems: 'center', flexWrap: 'wrap' }}>
                <button
                  onClick={async () => {
                    console.log('Refresh Posts button clicked');
                    try {
                      await getPosts();
                      console.log('Posts refreshed successfully');
                    } catch (error) {
                      console.error('Error refreshing posts:', error);
                    }
                  }}
                  style={{
                    ...synthwaveStyles.button,
                    cursor: 'pointer'
                  }}
                  className="synthwave-button"
                >
                  🔄 REFRESH POSTS
                </button>

                {/* Filter Controls */}
                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                  <label style={{ color: '#ff006e', fontSize: '0.9em', fontWeight: 'bold' }}>
                    Stage:
                  </label>
                  <select
                    value={stageFilter}
                    onChange={(e) => setStageFilter(e.target.value)}
                    style={{
                      background: 'rgba(0, 0, 0, 0.5)',
                      border: '1px solid #ff006e',
                      borderRadius: '5px',
                      color: '#ffffff',
                      padding: '5px 10px',
                      fontSize: '0.9em'
                    }}
                  >
                    <option value="all">All Stages</option>
                    <option value="triage">Triage</option>
                    <option value="research">Research</option>
                    <option value="response">Response</option>
                    <option value="editorial">Editorial</option>
                    <option value="post_queue">Post Queue</option>
                    <option value="completed">Completed</option>
                    <option value="rejected">Rejected</option>
                  </select>

                  <label style={{ color: '#ff006e', fontSize: '0.9em', fontWeight: 'bold', marginLeft: '15px' }}>
                    Status:
                  </label>
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    style={{
                      background: 'rgba(0, 0, 0, 0.5)',
                      border: '1px solid #ff006e',
                      borderRadius: '5px',
                      color: '#ffffff',
                      padding: '5px 10px',
                      fontSize: '0.9em'
                    }}
                  >
                    <option value="all">All Status</option>
                    <option value="pending">Pending</option>
                    <option value="processing">Processing</option>
                    <option value="completed">Completed</option>
                    <option value="failed">Failed</option>
                  </select>

                  {/* Clear Filters Button */}
                  {(stageFilter !== 'all' || statusFilter !== 'all') && (
                    <button
                      onClick={() => {
                        setStageFilter('all');
                        setStatusFilter('all');
                      }}
                      style={{
                        background: 'linear-gradient(45deg, #8338ec, #ff006e)',
                        border: 'none',
                        borderRadius: '5px',
                        color: '#ffffff',
                        padding: '5px 10px',
                        fontSize: '0.8em',
                        cursor: 'pointer',
                        marginLeft: '10px'
                      }}
                    >
                      🗑️ Clear
                    </button>
                  )}
                </div>
              </div>
              
              <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
                {(() => {
                  // Filter posts based on selected criteria
                  const filteredPosts = posts.filter(post => {
                    const postStage = post[8] || '';
                    const postStatus = post[9] || '';

                    const stageMatch = stageFilter === 'all' || postStage === stageFilter;
                    const statusMatch = statusFilter === 'all' || postStatus === statusFilter;

                    return stageMatch && statusMatch;
                  });

                  if (posts.length === 0) {
                    return (
                      <div style={{ textAlign: 'center', padding: '40px', color: '#8338ec' }}>
                        <div style={{ fontSize: '3em', marginBottom: '10px' }}>📭</div>
                        <div>No posts found in database</div>
                      </div>
                    );
                  }

                  if (filteredPosts.length === 0) {
                    return (
                      <div style={{ textAlign: 'center', padding: '40px', color: '#ff006e' }}>
                        <div style={{ fontSize: '3em', marginBottom: '10px' }}>🔍</div>
                        <div>No posts match the selected filters</div>
                        <div style={{ fontSize: '0.9em', marginTop: '10px', color: '#888' }}>
                          {stageFilter !== 'all' && `Stage: ${stageFilter}`}
                          {stageFilter !== 'all' && statusFilter !== 'all' && ' • '}
                          {statusFilter !== 'all' && `Status: ${statusFilter}`}
                        </div>
                      </div>
                    );
                  }

                  return filteredPosts.map((post, index) => (
                    <div key={index} style={{
                      background: 'rgba(58, 134, 255, 0.1)',
                      border: '1px solid rgba(58, 134, 255, 0.3)',
                      borderRadius: '10px',
                      padding: '20px',
                      marginBottom: '15px'
                    }}>
                      <h4 style={{ color: '#ffffff', margin: '0 0 10px 0' }}>{post[2]}</h4>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px', fontSize: '0.9em' }}>
                        <div>
                          <span style={{ color: '#ff006e' }}>Author:</span>
                          <span style={{ color: '#ffffff', marginLeft: '5px' }}>u/{post[3]}</span>
                        </div>
                        <div>
                          <span style={{ color: '#ff006e' }}>Queue Stage:</span>
                          <span style={{ color: '#00ff88', marginLeft: '5px' }}>{post[8] || 'N/A'}</span>
                        </div>
                        <div>
                          <span style={{ color: '#ff006e' }}>Status:</span>
                          <span style={{ color: '#8338ec', marginLeft: '5px' }}>{post[9] || 'N/A'}</span>
                        </div>
                      </div>
                      {post[5] && (
                        <div style={{ marginTop: '10px' }}>
                          <a href={post[5]} target="_blank" rel="noopener noreferrer" style={{
                            color: '#3a86ff',
                            textDecoration: 'none',
                            fontSize: '0.9em'
                          }}>
                            🔗 View Original Post
                          </a>
                        </div>
                      )}
                    </div>
                  ));
                })()}
              </div>

              {/* Filter Summary */}
              {(stageFilter !== 'all' || statusFilter !== 'all') && (
                <div style={{
                  marginTop: '15px',
                  padding: '10px',
                  background: 'rgba(255, 0, 110, 0.1)',
                  border: '1px solid rgba(255, 0, 110, 0.3)',
                  borderRadius: '8px',
                  textAlign: 'center',
                  fontSize: '0.9em'
                }}>
                  <span style={{ color: '#ff006e' }}>🔽 Filtering: </span>
                  <span style={{ color: '#ffffff' }}>
                    {(() => {
                      const filteredCount = posts.filter(post => {
                        const postStage = post[8] || '';
                        const postStatus = post[9] || '';
                        const stageMatch = stageFilter === 'all' || postStage === stageFilter;
                        const statusMatch = statusFilter === 'all' || postStatus === statusFilter;
                        return stageMatch && statusMatch;
                      }).length;

                      return `${filteredCount} of ${posts.length} posts shown`;
                    })()}
                  </span>
                  {stageFilter !== 'all' && (
                    <span style={{ color: '#00ff88', marginLeft: '10px' }}>Stage: {stageFilter}</span>
                  )}
                  {statusFilter !== 'all' && (
                    <span style={{ color: '#3a86ff', marginLeft: '10px' }}>Status: {statusFilter}</span>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'queues' && (
          <div>
            {/* Queue Control Dashboard */}
            <div style={synthwaveStyles.card} className="synthwave-card">
              <h2 style={synthwaveStyles.cardTitle}>🔄 QUEUE PROCESSING CONTROL</h2>
              
              {queueStatus && (
                <div style={synthwaveStyles.grid}>
                  {Object.entries(queueStatus.endpoint_status || {}).map(([stage, status]: [string, any]) => (
                    <div key={stage} style={{
                      background: status.available ? 'rgba(0, 255, 136, 0.1)' : 'rgba(255, 51, 102, 0.1)',
                      border: `2px solid ${status.available ? '#00ff88' : '#ff3366'}`,
                      borderRadius: '15px',
                      padding: '20px'
                    }}>
                      <h3 style={{ 
                        color: status.available ? '#00ff88' : '#ff3366',
                        marginBottom: '15px',
                        textTransform: 'uppercase'
                      }}>
                        {status.available ? '🟢' : '🔴'} {stage} STAGE
                      </h3>
                      
                      <div style={{ marginBottom: '15px' }}>
                        <div style={{ color: '#8338ec', marginBottom: '5px' }}>Load Status:</div>
                        <div style={{ color: '#ffffff' }}>{status.current_load}/{status.max_concurrent}</div>
                        
                        <div style={{ color: '#8338ec', marginBottom: '5px', marginTop: '10px' }}>Queue State:</div>
                        <div style={{ 
                          color: queueStates[stage] ? '#ff3366' : '#00ff88',
                          fontWeight: 'bold',
                          textShadow: queueStates[stage] ? '0 0 5px #ff3366' : '0 0 5px #00ff88'
                        }}>
                          {queueStates[stage] ? '⏸️ PAUSED' : '▶️ RUNNING'}
                        </div>
                      </div>
                      
                      <div style={{ display: 'flex', gap: '10px' }}>
                        <button 
                          onClick={() => pauseQueue(stage)}
                          style={{
                            ...synthwaveStyles.button,
                            background: queueStates[stage] 
                              ? 'linear-gradient(45deg, #ff3366, #ff006e)' 
                              : 'rgba(255, 51, 102, 0.3)',
                            boxShadow: queueStates[stage] 
                              ? '0 0 15px rgba(255, 51, 102, 0.6), 0 0 25px rgba(255, 51, 102, 0.4)' 
                              : 'none',
                            transform: queueStates[stage] ? 'scale(1.05)' : 'scale(1)',
                            transition: 'all 0.3s ease',
                            flex: 1
                          }}
                          className={queueStates[stage] ? 'synthwave-button' : ''}
                        >
                          ⏸️ PAUSE
                        </button>
                        <button 
                          onClick={() => resumeQueue(stage)}
                          style={{
                            ...synthwaveStyles.button,
                            background: !queueStates[stage] 
                              ? 'linear-gradient(45deg, #00ff88, #3a86ff)' 
                              : 'rgba(0, 255, 136, 0.3)',
                            boxShadow: !queueStates[stage] 
                              ? '0 0 15px rgba(0, 255, 136, 0.6), 0 0 25px rgba(0, 255, 136, 0.4)' 
                              : 'none',
                            transform: !queueStates[stage] ? 'scale(1.05)' : 'scale(1)',
                            transition: 'all 0.3s ease',
                            flex: 1
                          }}
                          className={!queueStates[stage] ? 'synthwave-button' : ''}
                        >
                          ▶️ RESUME
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              
            </div>
            
            {/* Queue Statistics */}
            {queueStats && (
              <div style={synthwaveStyles.card} className="synthwave-card">
                <h2 style={synthwaveStyles.cardTitle}>📊 QUEUE STATISTICS</h2>
                <div style={synthwaveStyles.grid}>
                  {(() => {
                    // Define color schemes for each stage
                    const stageColors = {
                      'triage': { bg: 'rgba(255, 0, 110, 0.1)', border: '#ff006e', text: '#ff006e' },
                      'research': { bg: 'rgba(131, 56, 236, 0.1)', border: '#8338ec', text: '#8338ec' },
                      'response': { bg: 'rgba(58, 134, 255, 0.1)', border: '#3a86ff', text: '#3a86ff' },
                      'editorial': { bg: 'rgba(0, 255, 136, 0.1)', border: '#00ff88', text: '#00ff88' },
                      'post_queue': { bg: 'rgba(255, 140, 0, 0.1)', border: '#ff8c00', text: '#ff8c00' },
                      'completed': { bg: 'rgba(46, 213, 115, 0.1)', border: '#2ed573', text: '#2ed573' },
                      'rejected': { bg: 'rgba(255, 51, 102, 0.1)', border: '#ff3366', text: '#ff3366' }
                    }

                    // Group stats by stage
                    const groupedStats: {[key: string]: any[]} = {}
                    queueStats.detailed_stats?.forEach((stat: any) => {
                      if (!groupedStats[stat.stage]) {
                        groupedStats[stat.stage] = []
                      }
                      groupedStats[stat.stage].push(stat)
                    })

                    // Define the order of stages
                    const stageOrder = ['triage', 'research', 'response', 'editorial']

                    // Calculate totals for each stage in the specified order
                    return stageOrder.filter(stage => groupedStats[stage]).map(stage => {
                      const stats = groupedStats[stage]
                      const colors = stageColors[stage as keyof typeof stageColors] || stageColors.triage
                      const totalPosts = stats.reduce((sum, stat) => sum + stat.count, 0)
                      const pendingPosts = stats.find(s => s.status === 'pending')?.count || 0
                      const processingPosts = stats.find(s => s.status === 'processing')?.count || 0
                      const completedPosts = stats.find(s => s.status === 'completed')?.count || 0
                      const failedPosts = stats.find(s => s.status === 'failed')?.count || 0

                      return (
                        <div key={stage} style={{
                          background: colors.bg,
                          border: `2px solid ${colors.border}`,
                          borderRadius: '15px',
                          padding: '25px',
                          boxShadow: `0 0 20px ${colors.border}40`
                        }}>
                          <h3 style={{
                            color: colors.text,
                            marginBottom: '20px',
                            textTransform: 'uppercase',
                            textAlign: 'center',
                            fontSize: '1.3em',
                            textShadow: `0 0 10px ${colors.border}`
                          }}>
                            🎯 {stage} STAGE
                          </h3>

                          {/* Total Posts Display */}
                          <div style={{
                            textAlign: 'center',
                            marginBottom: '25px',
                            padding: '15px',
                            background: 'rgba(0, 0, 0, 0.3)',
                            borderRadius: '10px'
                          }}>
                            <div style={{
                              fontSize: '3em',
                              color: colors.text,
                              fontWeight: 'bold',
                              textShadow: `0 0 15px ${colors.border}`
                            }}>
                              {totalPosts}
                            </div>
                            <div style={{ color: '#ffffff', fontSize: '1.1em' }}>
                              Total Posts
                            </div>
                          </div>

                          {/* Breakdown by Status */}
                          <div style={{ display: 'grid', gap: '12px' }}>
                            {pendingPosts > 0 && (
                              <div
                                onClick={() => getPendingPosts(stage)}
                                style={{
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  alignItems: 'center',
                                  background: 'rgba(255, 204, 0, 0.1)',
                                  padding: '8px 12px',
                                  borderRadius: '8px',
                                  border: '1px solid rgba(255, 204, 0, 0.3)',
                                  cursor: 'pointer',
                                  transition: 'all 0.2s ease'
                                }}
                                onMouseEnter={(e) => {
                                  e.currentTarget.style.background = 'rgba(255, 204, 0, 0.2)'
                                  e.currentTarget.style.transform = 'scale(1.02)'
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.background = 'rgba(255, 204, 0, 0.1)'
                                  e.currentTarget.style.transform = 'scale(1)'
                                }}>
                                <span style={{ color: '#ffcc00', fontWeight: 'bold' }}>
                                  {stage === 'triage' ? '⚡ New Posts:' :
                                   stage === 'research' ? '🔍 Research Pending:' :
                                   stage === 'response' ? '✍️ Response Pending:' :
                                   stage === 'editorial' ? '📝 Editorial Pending:' : '⏳ Pending:'}
                                </span>
                                <span style={{
                                  color: '#ffffff',
                                  fontSize: '1.3em',
                                  fontWeight: 'bold',
                                  textShadow: '0 0 8px #ffcc00'
                                }}>
                                  {pendingPosts}
                                </span>
                              </div>
                            )}
                            {processingPosts > 0 && (
                              <div style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                background: 'rgba(58, 134, 255, 0.1)',
                                padding: '8px 12px',
                                borderRadius: '8px',
                                border: '1px solid rgba(58, 134, 255, 0.3)'
                              }}>
                                <span style={{ color: '#3a86ff', fontWeight: 'bold' }}>🔄 Processing:</span>
                                <span style={{
                                  color: '#ffffff',
                                  fontSize: '1.2em',
                                  fontWeight: 'bold',
                                  textShadow: '0 0 8px #3a86ff'
                                }}>
                                  {processingPosts}
                                </span>
                              </div>
                            )}
                            {completedPosts > 0 && (
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span style={{ color: '#00ff88' }}>✅ Completed:</span>
                                <span style={{ color: '#ffffff', fontSize: '1.2em', fontWeight: 'bold' }}>
                                  {completedPosts}
                                </span>
                              </div>
                            )}
                            {failedPosts > 0 && (
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span style={{ color: '#ff3366' }}>❌ Failed:</span>
                                <span style={{ color: '#ffffff', fontSize: '1.2em', fontWeight: 'bold' }}>
                                  {failedPosts}
                                </span>
                              </div>
                            )}
                          </div>

                          {/* Additional Info */}
                          {stats.length > 0 && stats[0].oldest_post && (
                            <div style={{
                              marginTop: '20px',
                              padding: '12px',
                              background: 'rgba(0, 0, 0, 0.2)',
                              borderRadius: '8px',
                              fontSize: '0.9em'
                            }}>
                              <div style={{ color: colors.text }}>📅 Oldest Post:</div>
                              <div style={{ color: '#ffffff', marginTop: '5px' }}>
                                {new Date(stats[0].oldest_post).toLocaleString()}
                              </div>
                            </div>
                          )}
                        </div>
                      )
                    })
                  })()}

                  {/* Triage Rejects Box */}
                  {(() => {
                    const rejectedStats = queueStats.detailed_stats?.find((stat: any) => stat.stage === 'rejected' && stat.status === 'rejected')
                    const rejectedCount = rejectedStats?.count || 0
                    const colors = { bg: 'rgba(255, 51, 102, 0.1)', border: '#ff3366', text: '#ff3366' }

                    if (rejectedCount > 0) {
                      return (
                        <div style={{
                          background: colors.bg,
                          border: `2px solid ${colors.border}`,
                          borderRadius: '15px',
                          padding: '25px',
                          boxShadow: `0 0 20px ${colors.border}40`,
                          cursor: 'pointer',
                          transition: 'all 0.2s ease'
                        }}
                        onClick={getRejectedPosts}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.transform = 'scale(1.02)'
                          e.currentTarget.style.boxShadow = `0 0 30px ${colors.border}60`
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.transform = 'scale(1)'
                          e.currentTarget.style.boxShadow = `0 0 20px ${colors.border}40`
                        }}>
                          <h3 style={{
                            color: colors.text,
                            marginBottom: '20px',
                            textTransform: 'uppercase',
                            textAlign: 'center',
                            fontSize: '1.3em',
                            textShadow: `0 0 10px ${colors.border}`
                          }}>
                            🚫 TRIAGE REJECTS
                          </h3>

                          {/* Total Rejected Posts Display */}
                          <div style={{
                            textAlign: 'center',
                            marginBottom: '25px',
                            padding: '15px',
                            background: 'rgba(0, 0, 0, 0.3)',
                            borderRadius: '10px'
                          }}>
                            <div style={{
                              fontSize: '3em',
                              color: colors.text,
                              fontWeight: 'bold',
                              textShadow: `0 0 15px ${colors.border}`
                            }}>
                              {rejectedCount}
                            </div>
                            <div style={{ color: '#ffffff', fontSize: '1.1em' }}>
                              Rejected Posts
                            </div>
                          </div>

                          {/* Click to view details */}
                          <div style={{
                            textAlign: 'center',
                            color: '#ffffff',
                            fontSize: '0.9em',
                            opacity: 0.8
                          }}>
                            👆 Click to view rejection details
                          </div>
                        </div>
                      )
                    }
                    return null
                  })()}

                  {/* Fallback Events Box */}
                  {(() => {
                    const fallbackCount = fallbackStats?.total_count || 0
                    const colors = { bg: 'rgba(255, 165, 0, 0.1)', border: '#ffa500', text: '#ffa500' }

                    if (fallbackCount > 0) {
                      return (
                        <div style={{
                          background: colors.bg,
                          border: `2px solid ${colors.border}`,
                          borderRadius: '15px',
                          padding: '25px',
                          boxShadow: `0 0 20px ${colors.border}40`,
                          cursor: 'pointer',
                          transition: 'all 0.2s ease'
                        }}
                        onClick={getFallbackPosts}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.transform = 'scale(1.02)'
                          e.currentTarget.style.boxShadow = `0 0 30px ${colors.border}60`
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.transform = 'scale(1)'
                          e.currentTarget.style.boxShadow = `0 0 20px ${colors.border}40`
                        }}>
                          <h3 style={{
                            color: colors.text,
                            marginBottom: '20px',
                            textTransform: 'uppercase',
                            textAlign: 'center',
                            fontSize: '1.3em',
                            textShadow: `0 0 10px ${colors.border}`
                          }}>
                            ⚡ FALLBACK EVENTS
                          </h3>

                          {/* Total Fallback Posts Display */}
                          <div style={{
                            textAlign: 'center',
                            marginBottom: '25px',
                            padding: '15px',
                            background: 'rgba(0, 0, 0, 0.3)',
                            borderRadius: '10px'
                          }}>
                            <div style={{
                              fontSize: '3em',
                              color: colors.text,
                              fontWeight: 'bold',
                              textShadow: `0 0 15px ${colors.border}`
                            }}>
                              {fallbackCount}
                            </div>
                            <div style={{ color: '#ffffff', fontSize: '1.1em' }}>
                              API Failures
                            </div>
                          </div>

                          {/* Recent count if available */}
                          {fallbackStats?.recent_count > 0 && (
                            <div style={{
                              textAlign: 'center',
                              color: '#ffffff',
                              fontSize: '0.9em',
                              marginBottom: '10px'
                            }}>
                              {fallbackStats.recent_count} in last 24h
                            </div>
                          )}

                          {/* Click to view details */}
                          <div style={{
                            textAlign: 'center',
                            color: '#ffffff',
                            fontSize: '0.9em',
                            opacity: 0.8
                          }}>
                            👆 Click to manage affected posts
                          </div>
                        </div>
                      )
                    }
                    return null
                  })()}
                </div>

                {/* Refresh Button for Queue Statistics */}
                <div style={{ textAlign: 'center', marginTop: '20px' }}>
                  <button
                    onClick={async () => {
                      console.log('Refresh Statistics button clicked');
                      try {
                        await getQueueStats();
                        await getFallbackStats();
                        console.log('Queue stats refreshed successfully');
                      } catch (error) {
                        console.error('Error refreshing queue stats:', error);
                      }
                    }}
                    style={{
                      ...synthwaveStyles.button,
                      background: 'linear-gradient(45deg, #00ff88, #3a86ff)',
                      padding: '12px 24px',
                      fontSize: '1em',
                      cursor: 'pointer'
                    }}
                    className="synthwave-button"
                  >
                    🔄 REFRESH STATISTICS
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Retry Management Section */}
        {activeTab === 'queues' && (
          <div style={{...synthwaveStyles.card, marginTop: '20px'}} className="synthwave-card">
            <h2 style={synthwaveStyles.cardTitle}>🔄 RETRY MANAGEMENT</h2>

            <div style={{ display: 'grid', gap: '20px' }}>
              {/* Retry Settings */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '15px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', color: '#ff006e', fontSize: '0.9em' }}>
                    Retry Timeout (seconds):
                  </label>
                  <input
                    type="number"
                    min="30"
                    max="3600"
                    defaultValue={queueSettings?.retry_timeout_seconds?.value || "300"}
                    style={synthwaveStyles.input}
                    className="synthwave-input"
                    onBlur={async (e) => {
                      const value = e.target.value;
                      if (value) {
                        try {
                          await fetch(`${API_BASE}/queue/settings`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                              setting_key: 'retry_timeout_seconds',
                              setting_value: value
                            })
                          });
                          console.log(`Updated retry timeout to ${value} seconds`);
                        } catch (error) {
                          console.error('Failed to update retry timeout:', error);
                        }
                      }
                    }}
                  />
                  <small style={{ color: '#888', fontSize: '0.8em' }}>
                    How long to wait before retrying failed posts
                  </small>
                </div>

                <div>
                  <label style={{ display: 'block', marginBottom: '5px', color: '#ff006e', fontSize: '0.9em' }}>
                    Max Retry Attempts:
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="10"
                    defaultValue={queueSettings?.max_retry_attempts?.value || "3"}
                    style={synthwaveStyles.input}
                    className="synthwave-input"
                    onBlur={async (e) => {
                      const value = e.target.value;
                      if (value) {
                        try {
                          await fetch(`${API_BASE}/queue/settings`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                              setting_key: 'max_retry_attempts',
                              setting_value: value
                            })
                          });
                          console.log(`Updated max retry attempts to ${value}`);
                        } catch (error) {
                          console.error('Failed to update max retry attempts:', error);
                        }
                      }
                    }}
                  />
                  <small style={{ color: '#888', fontSize: '0.8em' }}>
                    Maximum retry attempts per post
                  </small>
                </div>

                <div>
                  <label style={{ display: 'block', marginBottom: '5px', color: '#ff006e', fontSize: '0.9em' }}>
                    Stuck Post Threshold (minutes):
                  </label>
                  <input
                    type="number"
                    min="5"
                    max="120"
                    defaultValue={queueSettings?.stuck_post_threshold_minutes?.value || "30"}
                    style={synthwaveStyles.input}
                    className="synthwave-input"
                    onBlur={async (e) => {
                      const value = e.target.value;
                      if (value) {
                        try {
                          await fetch(`${API_BASE}/queue/settings`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                              setting_key: 'stuck_post_threshold_minutes',
                              setting_value: value
                            })
                          });
                          console.log(`Updated stuck post threshold to ${value} minutes`);
                        } catch (error) {
                          console.error('Failed to update stuck post threshold:', error);
                        }
                      }
                    }}
                  />
                  <small style={{ color: '#888', fontSize: '0.8em' }}>
                    Minutes before a post is considered stuck
                  </small>
                </div>
              </div>

              {/* Action Buttons */}
              <div style={{ display: 'flex', gap: '15px', flexWrap: 'wrap' }}>
                <button
                  style={{
                    ...synthwaveStyles.button,
                    background: 'linear-gradient(45deg, #ff006e, #8338ec)',
                    color: 'white',
                    fontSize: '0.9em',
                    padding: '12px 20px'
                  }}
                  className="synthwave-button"
                  onClick={async () => {
                    try {
                      const response = await fetch(`${API_BASE}/queue/stuck-posts`);
                      const data = await response.json();
                      if (data.success) {
                        alert(`Found ${data.total_stuck} stuck posts:\n${data.stuck_posts.map((p: any) =>
                          `• Post ${p.id}: ${p.title.substring(0, 50)}... (${p.queue_stage}, retries: ${p.retry_count})`
                        ).join('\n')}`);
                      }
                    } catch (error) {
                      alert('Failed to detect stuck posts: ' + error);
                    }
                  }}
                >
                  🔍 Detect Stuck Posts
                </button>

                <button
                  style={{
                    ...synthwaveStyles.button,
                    background: 'linear-gradient(45deg, #00ff88, #00b4d8)',
                    color: 'black',
                    fontSize: '0.9em',
                    padding: '12px 20px'
                  }}
                  className="synthwave-button"
                  onClick={async () => {
                    try {
                      const response = await fetch(`${API_BASE}/queue/reset-stuck-posts`, {
                        method: 'POST'
                      });
                      const data = await response.json();
                      if (data.success) {
                        alert(`Reset ${data.total_reset} stuck posts for retry`);
                        // Refresh queue stats and settings
                        getQueueStats();
                        getQueueSettings();
                      }
                    } catch (error) {
                      alert('Failed to reset stuck posts: ' + error);
                    }
                  }}
                >
                  🔄 Reset Stuck Posts
                </button>
              </div>
            </div>
          </div>
        )}


        {activeTab === 'agents' && (
          <div>
            {/* Agent Configuration Overview */}
            {agentConfig && (
              <div style={synthwaveStyles.card} className="synthwave-card">
                <h2 style={synthwaveStyles.cardTitle}>🧠 AGENT CONFIGURATION & ENDPOINTS</h2>
                <div style={synthwaveStyles.grid}>
                  {Object.entries(agentConfig.config || {}).map(([stage, config]: [string, any]) => (
                    <div key={stage} style={{
                      background: 'rgba(58, 134, 255, 0.1)',
                      border: '1px solid rgba(58, 134, 255, 0.3)',
                      borderRadius: '15px',
                      padding: '20px'
                    }}>
                      <h3 style={{ color: '#3a86ff', marginBottom: '15px', textTransform: 'uppercase' }}>
                        {stage} AGENT
                      </h3>
                      
                      <div style={{ display: 'grid', gap: '15px', fontSize: '0.9em' }}>
                        {/* Endpoint Configuration */}
                        <div>
                          <label style={{ display: 'block', marginBottom: '8px', color: '#ff006e', fontSize: '0.9em' }}>Endpoint Type:</label>

                          {/* Radio Button Selection */}
                          <div style={{ marginBottom: '15px' }}>
                            <div style={{
                              display: 'flex',
                              flexDirection: 'column',
                              gap: '8px',
                              background: 'rgba(0, 0, 0, 0.2)',
                              padding: '10px',
                              borderRadius: '8px',
                              border: '1px solid rgba(255, 0, 110, 0.3)'
                            }}>
                              <label style={{
                                display: 'flex',
                                alignItems: 'center',
                                cursor: 'pointer',
                                fontSize: '0.85em',
                                color: endpointTypes[stage] === 'together' ? '#00ff88' : '#ffffff'
                              }}>
                                <input
                                  type="radio"
                                  name={`endpoint-type-${stage}`}
                                  value="together"
                                  checked={endpointTypes[stage] === 'together'}
                                  onChange={() => {
                                    console.log(`🟣 Selected Together API for ${stage}`)
                                    setEndpointTypes(prev => ({ ...prev, [stage]: 'together' }))
                                  }}
                                  style={{ marginRight: '8px', accentColor: '#00ff88' }}
                                />
                                🟣 Together AI
                              </label>

                              <label style={{
                                display: 'flex',
                                alignItems: 'center',
                                cursor: 'pointer',
                                fontSize: '0.85em',
                                color: endpointTypes[stage] === 'custom' || !endpointTypes[stage] ? '#00ff88' : '#ffffff'
                              }}>
                                <input
                                  type="radio"
                                  name={`endpoint-type-${stage}`}
                                  value="custom"
                                  checked={endpointTypes[stage] === 'custom' || !endpointTypes[stage]}
                                  onChange={() => {
                                    console.log(`🔧 Selected Custom Endpoint for ${stage}`)
                                    setEndpointTypes(prev => ({ ...prev, [stage]: 'custom' }))
                                  }}
                                  style={{ marginRight: '8px', accentColor: '#00ff88' }}
                                />
                                🔧 Custom Endpoint (Ollama/LM Studio/Other)
                              </label>
                            </div>
                          </div>

                          {/* Custom Endpoint Input - Only show when custom is selected */}
                          {(endpointTypes[stage] === 'custom' || !endpointTypes[stage]) && (
                            <div style={{ marginBottom: '10px' }}>
                              <label style={{ display: 'block', marginBottom: '5px', color: '#3a86ff', fontSize: '0.85em' }}>Custom Endpoint URL:</label>
                              <input
                                id={`endpoint-${stage}`}
                                type="text"
                                defaultValue={currentEndpoints[stage] || config.endpoint}
                                key={`${stage}-${currentEndpoints[stage] || config.endpoint}`}
                                placeholder="http://localhost:11434 (base URL only)"
                                style={{
                                  ...synthwaveStyles.input,
                                  fontSize: '0.9em',
                                  marginBottom: '5px'
                                }}
                                className="synthwave-input"
                                onBlur={async (e) => {
                                  const url = e.target.value.trim()
                                  if (url && url !== config.endpoint) {
                                    console.log(`Auto-polling models for updated endpoint: ${url}`)
                                    setCurrentEndpoints(prev => ({ ...prev, [stage]: url }))
                                    await testEndpointAndFetchModels(url)
                                  }
                                }}
                              />
                              <button
                                onClick={async () => {
                                  const input = document.getElementById(`endpoint-${stage}`) as HTMLInputElement
                                  const url = input?.value.trim()

                                  if (!url) {
                                    alert('⚠️ Please enter an endpoint URL')
                                    return
                                  }

                                  console.log(`Testing endpoint for ${stage}:`, url)
                                  const result = await testEndpointAndFetchModels(url, stage)

                                  if (result.success) {
                                    alert(`✅ Endpoint connected successfully!\n\nFound ${result.models.length} models:\n${result.models.slice(0, 5).join('\n')}${result.models.length > 5 ? '\n...' : ''}`)
                                  } else {
                                    alert(`❌ Failed to connect to endpoint:\n\n${result.error}`)
                                  }
                                }}
                                disabled={testingEndpoint === stage}
                                style={{
                                  ...synthwaveStyles.button,
                                  background: testingEndpoint === stage
                                    ? 'rgba(255, 255, 255, 0.1)'
                                    : 'linear-gradient(45deg, #00ff88, #3a86ff)',
                                  fontSize: '0.8em',
                                  padding: '6px 12px',
                                  cursor: testingEndpoint === stage ? 'not-allowed' : 'pointer',
                                  opacity: testingEndpoint === stage ? 0.6 : 1
                                }}
                                className={testingEndpoint === stage ? '' : 'synthwave-button'}
                              >
                                {testingEndpoint === stage ? (
                                  <>
                                    <span className="loading-spinner" style={{marginRight: '6px'}}></span>
                                    TESTING...
                                  </>
                                ) : (
                                  '🔍 TEST ENDPOINT'
                                )}
                              </button>
                            </div>
                          )}

                          {/* Together API Status Display */}
                          {endpointTypes[stage] === 'together' && (
                            <div style={{
                              background: 'rgba(0, 255, 136, 0.1)',
                              border: '1px solid rgba(0, 255, 136, 0.3)',
                              borderRadius: '8px',
                              padding: '10px',
                              fontSize: '0.85em',
                              color: '#00ff88'
                            }}>
                              🟣 <strong>Together AI Endpoint Active</strong><br/>
                              <small style={{ color: '#8ecae6' }}>
                                Enterprise-grade models with function calling support<br/>
                                Model: {currentModels[stage] || 'No model selected'}
                              </small>
                            </div>
                          )}
                        </div>

                        {/* Model Selection */}
                        <div>
                          <label style={{ display: 'block', marginBottom: '5px', color: '#ff006e', fontSize: '0.9em' }}>Selected Model:</label>
                          <select
                            defaultValue={currentModels[stage] || config.model}
                            key={`model-${stage}-${currentModels[stage] || config.model}-${endpointTypes[stage]}`} // Force re-render when model or endpoint type changes
                            style={{
                              ...synthwaveStyles.input,
                              fontSize: '0.9em',
                              cursor: 'pointer'
                            }}
                            className="synthwave-input"
                            onChange={(e) => {
                              const newModel = e.target.value
                              console.log(`🔄 Model changed for ${stage}: ${newModel}`)
                              setCurrentModels(prev => ({ ...prev, [stage]: newModel }))
                            }}
                          >
                            <option value={currentModels[stage] || config.model}>
                              {currentModels[stage] || config.model} (current)
                            </option>

                            {/* Show Together AI models when Together is selected */}
                            {endpointTypes[stage] === 'together' ? (
                              [
                                'Qwen/Qwen3-Next-80B-A3B-Thinking',
                                'Qwen/Qwen2.5-7B-Instruct-Turbo',
                                'meta-llama/Llama-3.1-8B-Instruct-Turbo',
                                'meta-llama/Llama-3.1-70B-Instruct-Turbo',
                                'meta-llama/Llama-3.1-405B-Instruct-Turbo',
                                'mistralai/Mixtral-8x7B-Instruct-v0.1',
                                'mistralai/Mistral-7B-Instruct-v0.3'
                              ].map((model: string, idx: number) => {
                                const currentModel = currentModels[stage] || config.model
                                return model !== currentModel && (
                                  <option key={idx} value={model}>{model}</option>
                                )
                              })
                            ) : (
                              /* Show custom endpoint models */
                              availableModels[currentEndpoints[stage] || config.endpoint]?.map((model: string, idx: number) => {
                                const currentModel = currentModels[stage] || config.model
                                return model !== currentModel && (
                                  <option key={idx} value={model}>{model}</option>
                                )
                              })
                            )}
                          </select>
                          {(() => {
                            const currentEndpointType = endpointTypes[stage] || 'custom'
                            const currentEndpoint = currentEndpoints[stage] || config.endpoint

                            if (currentEndpointType === 'together') {
                              return (
                                <div style={{ color: '#8338ec', fontSize: '0.8em', marginTop: '5px' }}>
                                  ✅ Together AI configured
                                  <br />
                                  <small style={{ color: '#666', fontSize: '0.7em' }}>
                                    Model: {currentModels[stage] || 'No model selected'}
                                    <br />
                                    <span style={{ color: '#00ff88' }}>💾 Settings auto-saved</span>
                                  </small>
                                </div>
                              )
                            } else {
                              return availableModels[currentEndpoint] ? (
                                <div style={{ color: '#8338ec', fontSize: '0.8em', marginTop: '5px' }}>
                                  ✅ {availableModels[currentEndpoint].length} models available
                                  <br />
                                  <small style={{ color: '#666', fontSize: '0.7em' }}>
                                    Endpoint: {currentEndpoint}
                                    <br />
                                    <span style={{ color: '#00ff88' }}>💾 Settings auto-saved</span>
                                  </small>
                                </div>
                              ) : currentEndpoint ? (
                                <div style={{ color: '#ff006e', fontSize: '0.8em', marginTop: '5px' }}>
                                  🔍 Loading models from endpoint...
                                </div>
                              ) : (
                                <div style={{ color: '#666', fontSize: '0.8em', marginTop: '5px' }}>
                                  ⚠️ Enter endpoint URL to see available models
                                </div>
                              )
                            }
                          })()}
                        </div>

                        {/* Current Configuration Display */}
                        <div style={{ 
                          background: 'rgba(0, 0, 0, 0.2)', 
                          padding: '15px', 
                          borderRadius: '8px',
                          fontSize: '0.85em'
                        }}>
                          <div style={{ marginBottom: '8px' }}>
                            <span style={{ color: '#ff006e' }}>Max Concurrent:</span>
                            <span style={{ color: '#ffffff', marginLeft: '10px' }}>{config.max_concurrent}</span>
                          </div>
                          <div style={{ marginBottom: '8px' }}>
                            <span style={{ color: '#ff006e' }}>Cost Per Token:</span>
                            <span style={{ color: '#ffffff', marginLeft: '10px' }}>${config.cost_per_token}</span>
                          </div>
                          <div>
                            <span style={{ color: '#ff006e' }}>Description:</span>
                            <div style={{ color: '#8338ec', marginTop: '5px', lineHeight: '1.3' }}>
                              {config.description}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {/* System Prompts Management */}
            <div style={synthwaveStyles.card} className="synthwave-card">
              <h2 style={synthwaveStyles.cardTitle}>📝 SYSTEM PROMPT MANAGEMENT</h2>
              {(() => {
                // Define the correct pipeline order
                const stageOrder = ['triage', 'research', 'response', 'editorial'];

                // Sort prompts according to the pipeline order
                const sortedPrompts = [...agentPrompts].sort((a, b) => {
                  const indexA = stageOrder.indexOf(a.agent_stage);
                  const indexB = stageOrder.indexOf(b.agent_stage);

                  // If stage not found in order, put it at the end
                  if (indexA === -1) return 1;
                  if (indexB === -1) return -1;

                  return indexA - indexB;
                });

                return sortedPrompts.map((prompt, index) => (
                <div key={index} style={{
                  background: 'rgba(131, 56, 236, 0.1)',
                  border: '1px solid rgba(131, 56, 236, 0.3)',
                  borderRadius: '15px',
                  padding: '25px',
                  marginBottom: '20px'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
                    <h3 style={{ color: '#8338ec', margin: 0, textTransform: 'uppercase' }}>
                      {prompt.agent_stage} AGENT (v{prompt.version})
                    </h3>
                    <button 
                      onClick={() => setEditingPrompt(editingPrompt?.agent_stage === prompt.agent_stage ? null : prompt)}
                      style={{
                        ...synthwaveStyles.button,
                        background: editingPrompt?.agent_stage === prompt.agent_stage 
                          ? 'linear-gradient(45deg, #ff3366, #ff006e)' 
                          : 'linear-gradient(45deg, #00ff88, #3a86ff)'
                      }}
                      className="synthwave-button"
                    >
                      {editingPrompt?.agent_stage === prompt.agent_stage ? '❌ CANCEL' : '✏️ EDIT'}
                    </button>
                  </div>
                  
                  {editingPrompt?.agent_stage === prompt.agent_stage ? (
                    <div>
                      <textarea
                        value={editingPrompt.system_prompt}
                        onChange={(e) => setEditingPrompt({ ...editingPrompt, system_prompt: e.target.value })}
                        style={{
                          ...synthwaveStyles.input,
                          minHeight: '200px',
                          fontFamily: "'Courier New', monospace",
                          fontSize: '13px',
                          resize: 'vertical'
                        }}
                        placeholder="Enter system prompt for this agent..."
                        className="synthwave-input"
                      />
                      <div style={{ display: 'flex', gap: '15px', marginTop: '15px' }}>
                        <button 
                          onClick={() => updateAgentPrompt(editingPrompt.agent_stage, editingPrompt.system_prompt)}
                          style={{
                            ...synthwaveStyles.button,
                            background: 'linear-gradient(45deg, #00ff88, #3a86ff)',
                            flex: 1
                          }}
                          className="synthwave-button"
                        >
                          💾 SAVE PROMPT
                        </button>
                        <button 
                          onClick={() => setEditingPrompt(null)}
                          style={{
                            ...synthwaveStyles.button,
                            background: 'linear-gradient(45deg, #ff3366, #ff006e)',
                            flex: 1
                          }}
                          className="synthwave-button"
                        >
                          ❌ CANCEL
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div style={{
                      background: 'rgba(0, 0, 0, 0.3)',
                      borderRadius: '10px',
                      padding: '20px',
                      fontFamily: "'Courier New', monospace",
                      fontSize: '13px',
                      maxHeight: '200px',
                      overflowY: 'auto',
                      color: '#ffffff',
                      lineHeight: '1.5'
                    }}>
                      {prompt.system_prompt || (
                        <div style={{ color: '#8338ec', fontStyle: 'italic' }}>
                          No system prompt configured for this agent
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ));
              })()}

              <button 
                onClick={refreshAgentData}
                style={{
                  ...synthwaveStyles.button,
                  background: 'linear-gradient(45deg, #8338ec, #ff006e)',
                  marginTop: '20px'
                }}
                className="synthwave-button"
              >
                🔄 REFRESH AGENT DATA
              </button>
            </div>
          </div>
        )}

        {activeTab === 'post' && (
          <div>
            {/* Post Review Dashboard */}
            <div style={synthwaveStyles.card} className="synthwave-card">
              <h2 style={synthwaveStyles.cardTitle}>📝 POST REVIEW & SUBMISSION</h2>

              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '20px'
              }}>
                <span style={{ color: '#ffffff', fontSize: '1.1em' }}>
                  Ready for human review and Reddit posting
                </span>
                <button
                  onClick={getCompletedPosts}
                  style={{
                    ...synthwaveStyles.button,
                    background: 'linear-gradient(45deg, #ff006e, #8338ec)',
                    padding: '8px 16px',
                    fontSize: '0.9em'
                  }}
                  className="synthwave-button"
                >
                  🔄 REFRESH LIST
                </button>
              </div>

              <div style={{
                display: 'grid',
                gap: '15px',
                maxHeight: '500px',
                overflow: 'auto'
              }}>
                {completedPosts.length === 0 ? (
                  <div style={{
                    textAlign: 'center',
                    color: '#8892b0',
                    fontSize: '1.1em',
                    padding: '40px'
                  }}>
                    📭 No completed editorial posts ready for review
                  </div>
                ) : (
                  completedPosts.map((post: any, index: number) => (
                    <div
                      key={post.id}
                      onClick={() => handlePostReview(post)}
                      style={{
                        background: 'rgba(255, 255, 255, 0.05)',
                        border: '1px solid rgba(255, 0, 110, 0.2)',
                        borderRadius: '10px',
                        padding: '15px',
                        cursor: 'pointer',
                        transition: 'all 0.2s ease'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = 'rgba(255, 0, 110, 0.1)'
                        e.currentTarget.style.borderColor = 'rgba(255, 0, 110, 0.5)'
                        e.currentTarget.style.transform = 'scale(1.02)'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)'
                        e.currentTarget.style.borderColor = 'rgba(255, 0, 110, 0.2)'
                        e.currentTarget.style.transform = 'scale(1)'
                      }}
                    >
                      <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        marginBottom: '10px'
                      }}>
                        <h3 style={{
                          color: '#ff006e',
                          fontSize: '1.1em',
                          margin: 0,
                          flex: 1,
                          marginRight: '15px'
                        }}>
                          {post.title}
                        </h3>
                        <span style={{
                          color: '#3a86ff',
                          fontSize: '0.85em',
                          whiteSpace: 'nowrap'
                        }}>
                          ✨ Ready to Post
                        </span>
                      </div>

                      <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        fontSize: '0.85em',
                        color: '#8892b0'
                      }}>
                        <span>#{post.id}</span>
                        <span>👤 {post.author}</span>
                        <span>🔗 {post.reddit_id}</span>
                        <span>📅 {new Date(post.created_utc).toLocaleDateString()}</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Pending Posts Modal */}
      {pendingPostsModal.visible && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000
        }}>
          <div style={{
            background: 'linear-gradient(135deg, #0f0f23 0%, #1a1a3a 50%, #0f0f23 100%)',
            border: '2px solid #ff006e',
            borderRadius: '15px',
            padding: '30px',
            maxWidth: '80%',
            maxHeight: '80%',
            overflow: 'auto',
            minWidth: '600px',
            boxShadow: '0 0 50px rgba(255, 0, 110, 0.3)'
          }}>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '25px'
            }}>
              <h2 style={{
                color: '#ff006e',
                fontSize: '1.8em',
                textTransform: 'uppercase',
                textShadow: '0 0 10px #ff006e',
                margin: 0
              }}>
                {pendingPostsModal.stage === 'triage' ? '⚡ New Posts' :
                 pendingPostsModal.stage === 'research' ? '🔍 Research Pending' :
                 pendingPostsModal.stage === 'response' ? '✍️ Response Pending' :
                 pendingPostsModal.stage === 'editorial' ? '📝 Editorial Pending' : 'Pending Posts'}
                 <span style={{ color: '#ffffff', marginLeft: '10px' }}>
                   ({pendingPostsModal.posts.length})
                 </span>
              </h2>
              <button
                onClick={() => setPendingPostsModal({visible: false, stage: '', posts: []})}
                style={{
                  background: 'transparent',
                  border: '2px solid #ff006e',
                  borderRadius: '50%',
                  width: '40px',
                  height: '40px',
                  color: '#ff006e',
                  fontSize: '20px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
              >
                ×
              </button>
            </div>

            <div style={{
              display: 'grid',
              gap: '15px',
              maxHeight: '400px',
              overflow: 'auto'
            }}>
              {pendingPostsModal.posts.length === 0 ? (
                <div style={{
                  textAlign: 'center',
                  color: '#ffffff',
                  fontSize: '1.2em',
                  padding: '50px'
                }}>
                  No pending posts found
                </div>
              ) : (
                pendingPostsModal.posts.map((post: any, index: number) => {
                  const isExpanded = expandedPosts[post.id]
                  const previousStage = getPreviousStage(pendingPostsModal.stage)
                  const previousStageResults = isExpanded?.stage_results?.[previousStage]

                  return (
                    <div key={post.id}>
                      {/* Main Post Item */}
                      <div
                        onClick={() => handlePostClick(post)}
                        style={{
                          background: isExpanded ? 'rgba(255, 0, 110, 0.1)' : 'rgba(255, 255, 255, 0.05)',
                          border: isExpanded ? '2px solid rgba(255, 0, 110, 0.5)' : '1px solid rgba(255, 0, 110, 0.2)',
                          borderRadius: '10px',
                          padding: '15px',
                          transition: 'all 0.2s ease',
                          cursor: 'pointer'
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = isExpanded ? 'rgba(255, 0, 110, 0.15)' : 'rgba(255, 255, 255, 0.1)'
                          e.currentTarget.style.transform = 'scale(1.02)'
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = isExpanded ? 'rgba(255, 0, 110, 0.1)' : 'rgba(255, 255, 255, 0.05)'
                          e.currentTarget.style.transform = 'scale(1)'
                        }}
                      >
                        <div style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'flex-start',
                          marginBottom: '10px'
                        }}>
                          <div style={{
                            color: '#ff006e',
                            fontSize: '0.9em',
                            fontWeight: 'bold'
                          }}>
                            #{index + 1} • u/{post.author}
                          </div>
                          <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            color: '#ffcc00',
                            fontSize: '0.8em'
                          }}>
                            {post.retry_count > 0 && `Retry: ${post.retry_count}`}
                            <span style={{ color: '#00ff88' }}>
                              {isExpanded ? '🔼 Click to collapse' : '🔽 Click to expand'}
                            </span>
                          </div>
                        </div>
                        <div style={{
                          color: '#ffffff',
                          fontSize: '1.1em',
                          lineHeight: '1.4',
                          marginBottom: '10px'
                        }}>
                          {post.title}
                        </div>
                        <div style={{
                          color: '#8892b0',
                          fontSize: '0.85em',
                          display: 'flex',
                          justifyContent: 'space-between'
                        }}>
                          <span>Post ID: {post.reddit_id}</span>
                          <span>
                            {new Date(post.created_utc).toLocaleString()}
                          </span>
                        </div>
                      </div>

                      {/* Expanded Previous Stage Results */}
                      {isExpanded && previousStage && previousStageResults && (
                        <div style={{
                          marginTop: '10px',
                          marginLeft: '20px',
                          background: 'rgba(0, 0, 0, 0.3)',
                          border: '1px solid rgba(58, 134, 255, 0.3)',
                          borderRadius: '8px',
                          padding: '15px'
                        }}>
                          <h4 style={{
                            color: '#3a86ff',
                            margin: '0 0 10px 0',
                            fontSize: '1em',
                            textTransform: 'uppercase'
                          }}>
                            📋 {previousStage} Stage Results
                          </h4>

                          <div style={{
                            background: 'rgba(255, 255, 255, 0.05)',
                            borderRadius: '5px',
                            padding: '12px',
                            fontSize: '0.9em',
                            color: '#ffffff',
                            lineHeight: '1.6',
                            maxHeight: '300px',
                            overflow: 'auto',
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word'
                          }}>
                            {formatStageContent(previousStageResults.content)}
                          </div>

                          <div style={{
                            marginTop: '8px',
                            fontSize: '0.75em',
                            color: '#8892b0'
                          }}>
                            <span>Completed: {new Date(previousStageResults.created_at).toLocaleString()}</span>
                          </div>
                        </div>
                      )}

                      {/* Show message if no previous stage */}
                      {isExpanded && !previousStage && (
                        <div style={{
                          marginTop: '10px',
                          marginLeft: '20px',
                          background: 'rgba(255, 140, 0, 0.1)',
                          border: '1px solid rgba(255, 140, 0, 0.3)',
                          borderRadius: '8px',
                          padding: '15px',
                          textAlign: 'center',
                          color: '#ff8c00'
                        }}>
                          📭 This is the first stage - no previous results to show
                        </div>
                      )}
                    </div>
                  )
                })
              )}
            </div>

            <div style={{
              marginTop: '25px',
              textAlign: 'center'
            }}>
              <button
                onClick={() => setPendingPostsModal({visible: false, stage: '', posts: []})}
                style={{
                  ...synthwaveStyles.button,
                  background: 'linear-gradient(45deg, #ff006e, #8338ec)',
                  padding: '12px 30px'
                }}
                className="synthwave-button"
              >
                CLOSE
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rejected Posts Modal */}
      {rejectedPostsModal.visible && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000
        }}>
          <div style={{
            background: 'linear-gradient(135deg, #0f0f23 0%, #1a1a3a 50%, #0f0f23 100%)',
            border: '2px solid #ff3366',
            borderRadius: '15px',
            padding: '30px',
            maxWidth: '90%',
            maxHeight: '90%',
            overflow: 'auto',
            minWidth: '800px',
            boxShadow: '0 0 50px rgba(255, 51, 102, 0.3)'
          }}>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '25px'
            }}>
              <h2 style={{
                color: '#ff3366',
                fontSize: '1.8em',
                textTransform: 'uppercase',
                textShadow: '0 0 10px #ff3366',
                margin: 0
              }}>
                🚫 TRIAGE REJECTS
                <span style={{ color: '#ffffff', marginLeft: '10px' }}>
                  ({rejectedPostsModal.posts.length})
                </span>
              </h2>
              <button
                onClick={() => setRejectedPostsModal({visible: false, posts: [], selectedPost: null})}
                style={{
                  background: 'transparent',
                  border: '2px solid #ff3366',
                  borderRadius: '50%',
                  width: '40px',
                  height: '40px',
                  color: '#ff3366',
                  fontSize: '20px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
              >
                ×
              </button>
            </div>

            {rejectedPostsModal.selectedPost ? (
              /* Post Detail View */
              <div>
                <button
                  onClick={() => setRejectedPostsModal(prev => ({...prev, selectedPost: null}))}
                  style={{
                    background: 'transparent',
                    border: '1px solid #ff3366',
                    borderRadius: '5px',
                    color: '#ff3366',
                    padding: '8px 16px',
                    cursor: 'pointer',
                    marginBottom: '20px'
                  }}
                >
                  ← Back to List
                </button>

                <div style={{
                  background: 'rgba(255, 51, 102, 0.1)',
                  border: '1px solid rgba(255, 51, 102, 0.3)',
                  borderRadius: '10px',
                  padding: '20px'
                }}>
                  <h3 style={{
                    color: '#ff3366',
                    marginBottom: '15px',
                    fontSize: '1.4em'
                  }}>
                    📋 POST DETAILS
                  </h3>

                  <div style={{ marginBottom: '20px' }}>
                    <div style={{ color: '#ffffff', fontSize: '1.2em', fontWeight: 'bold', marginBottom: '10px' }}>
                      {rejectedPostsModal.selectedPost.title}
                    </div>
                    <div style={{ color: '#8892b0', fontSize: '0.9em', marginBottom: '10px' }}>
                      By u/{rejectedPostsModal.selectedPost.author} • {new Date(rejectedPostsModal.selectedPost.created_utc).toLocaleString()}
                    </div>
                    {rejectedPostsModal.selectedPost.body && (
                      <div style={{
                        background: 'rgba(255, 255, 255, 0.05)',
                        borderRadius: '5px',
                        padding: '15px',
                        color: '#ffffff',
                        lineHeight: '1.6',
                        maxHeight: '300px',
                        overflow: 'auto',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        marginBottom: '20px'
                      }}>
                        {rejectedPostsModal.selectedPost.body}
                      </div>
                    )}
                  </div>

                  <h4 style={{
                    color: '#ff3366',
                    marginBottom: '15px',
                    fontSize: '1.2em'
                  }}>
                    🚫 REJECTION REASONING
                  </h4>

                  <div style={{
                    background: 'rgba(0, 0, 0, 0.3)',
                    border: '1px solid rgba(255, 51, 102, 0.3)',
                    borderRadius: '8px',
                    padding: '15px',
                    color: '#ffffff',
                    lineHeight: '1.6'
                  }}>
                    {rejectedPostsModal.selectedPost.rejection_reasoning}
                  </div>
                </div>
              </div>
            ) : (
              /* Posts List View */
              <div style={{
                display: 'grid',
                gap: '15px',
                maxHeight: '500px',
                overflow: 'auto'
              }}>
                {rejectedPostsModal.posts.length === 0 ? (
                  <div style={{
                    textAlign: 'center',
                    color: '#ffffff',
                    fontSize: '1.2em',
                    padding: '50px'
                  }}>
                    No rejected posts found
                  </div>
                ) : (
                  rejectedPostsModal.posts.map((post: any) => (
                    <div
                      key={post.id}
                      onClick={() => setRejectedPostsModal(prev => ({...prev, selectedPost: post}))}
                      style={{
                        background: 'rgba(255, 51, 102, 0.1)',
                        border: '1px solid rgba(255, 51, 102, 0.3)',
                        borderRadius: '10px',
                        padding: '20px',
                        cursor: 'pointer',
                        transition: 'all 0.2s ease'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = 'rgba(255, 51, 102, 0.2)'
                        e.currentTarget.style.transform = 'scale(1.02)'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = 'rgba(255, 51, 102, 0.1)'
                        e.currentTarget.style.transform = 'scale(1)'
                      }}
                    >
                      <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        marginBottom: '10px'
                      }}>
                        <h4 style={{
                          color: '#ffffff',
                          fontSize: '1.1em',
                          margin: 0,
                          flex: 1,
                          lineHeight: '1.4'
                        }}>
                          {post.title}
                        </h4>
                        <span style={{
                          background: 'rgba(255, 51, 102, 0.2)',
                          color: '#ff3366',
                          padding: '4px 8px',
                          borderRadius: '12px',
                          fontSize: '0.8em',
                          marginLeft: '10px',
                          whiteSpace: 'nowrap'
                        }}>
                          REJECTED
                        </span>
                      </div>

                      <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        fontSize: '0.9em',
                        color: '#8892b0'
                      }}>
                        <span>
                          by u/{post.author}
                        </span>
                        <span>
                          {new Date(post.created_utc).toLocaleString()}
                        </span>
                      </div>

                      {/* Rejection reason preview */}
                      <div style={{
                        marginTop: '10px',
                        fontSize: '0.9em',
                        color: '#ffffff',
                        opacity: 0.8,
                        lineHeight: '1.4'
                      }}>
                        {post.rejection_reasoning.length > 150
                          ? `${post.rejection_reasoning.substring(0, 150)}...`
                          : post.rejection_reasoning}
                      </div>

                      <div style={{
                        marginTop: '10px',
                        fontSize: '0.8em',
                        color: '#ff3366',
                        textAlign: 'right'
                      }}>
                        👆 Click to view full details
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            <div style={{
              marginTop: '25px',
              textAlign: 'center'
            }}>
              <button
                onClick={() => setRejectedPostsModal({visible: false, posts: [], selectedPost: null})}
                style={{
                  ...synthwaveStyles.button,
                  background: 'linear-gradient(45deg, #ff3366, #ff006e)',
                  padding: '12px 30px'
                }}
                className="synthwave-button"
              >
                CLOSE
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Fallback Posts Modal */}
      {fallbackPostsModal.visible && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000
        }}>
          <div style={{
            background: 'linear-gradient(135deg, #0f0f23 0%, #1a1a3a 50%, #0f0f23 100%)',
            border: '2px solid #ffa500',
            borderRadius: '15px',
            padding: '30px',
            maxWidth: '90%',
            maxHeight: '90%',
            overflow: 'auto',
            minWidth: '800px',
            boxShadow: '0 0 50px rgba(255, 165, 0, 0.3)'
          }}>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '25px'
            }}>
              <h2 style={{
                color: '#ffa500',
                fontSize: '1.8em',
                textTransform: 'uppercase',
                textShadow: '0 0 10px #ffa500',
                margin: 0
              }}>
                ⚡ FALLBACK EVENTS
                <span style={{ color: '#ffffff', marginLeft: '10px' }}>
                  ({fallbackPostsModal.posts.length})
                </span>
              </h2>
              <button
                onClick={() => setFallbackPostsModal({visible: false, posts: [], selectedPosts: [], timeoutMinutes: 30})}
                style={{
                  background: 'transparent',
                  border: '2px solid #ffa500',
                  borderRadius: '50%',
                  width: '40px',
                  height: '40px',
                  color: '#ffa500',
                  fontSize: '20px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
              >
                ×
              </button>
            </div>

            {/* Retry Controls */}
            <div style={{
              background: 'rgba(255, 165, 0, 0.1)',
              border: '1px solid rgba(255, 165, 0, 0.3)',
              borderRadius: '10px',
              padding: '20px',
              marginBottom: '20px'
            }}>
              <h3 style={{ color: '#ffa500', marginBottom: '15px', fontSize: '1.2em' }}>
                🔄 RETRY CONFIGURATION
              </h3>

              <div style={{ display: 'flex', alignItems: 'center', gap: '15px', marginBottom: '15px' }}>
                <label style={{ color: '#ffffff', minWidth: '150px' }}>
                  Retry timeout (minutes):
                </label>
                <input
                  type="number"
                  value={fallbackPostsModal.timeoutMinutes}
                  onChange={(e) => setFallbackPostsModal(prev => ({
                    ...prev,
                    timeoutMinutes: parseInt(e.target.value) || 30
                  }))}
                  style={{
                    background: 'rgba(0, 0, 0, 0.3)',
                    border: '1px solid #ffa500',
                    borderRadius: '5px',
                    color: '#ffffff',
                    padding: '8px 12px',
                    width: '100px'
                  }}
                  min="1"
                  max="1440"
                />
                <span style={{ color: '#8892b0', fontSize: '0.9em' }}>
                  Posts will be retried after this delay
                </span>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  onClick={() => {
                    const allPostIds = fallbackPostsModal.posts.map(p => p.post_id)
                    setFallbackPostsModal(prev => ({ ...prev, selectedPosts: allPostIds }))
                  }}
                  style={{
                    background: 'transparent',
                    border: '1px solid #ffa500',
                    borderRadius: '5px',
                    color: '#ffa500',
                    padding: '8px 16px',
                    cursor: 'pointer',
                    fontSize: '0.9em'
                  }}
                >
                  Select All
                </button>
                <button
                  onClick={() => setFallbackPostsModal(prev => ({ ...prev, selectedPosts: [] }))}
                  style={{
                    background: 'transparent',
                    border: '1px solid #ffa500',
                    borderRadius: '5px',
                    color: '#ffa500',
                    padding: '8px 16px',
                    cursor: 'pointer',
                    fontSize: '0.9em'
                  }}
                >
                  Clear Selection
                </button>
                <button
                  onClick={retryFallbackPosts}
                  disabled={fallbackPostsModal.selectedPosts.length === 0}
                  style={{
                    background: fallbackPostsModal.selectedPosts.length > 0 ? 'linear-gradient(45deg, #ffa500, #ff8c00)' : 'rgba(100, 100, 100, 0.3)',
                    border: 'none',
                    borderRadius: '5px',
                    color: '#ffffff',
                    padding: '8px 16px',
                    cursor: fallbackPostsModal.selectedPosts.length > 0 ? 'pointer' : 'not-allowed',
                    fontSize: '0.9em',
                    fontWeight: 'bold'
                  }}
                >
                  Retry Selected ({fallbackPostsModal.selectedPosts.length})
                </button>
              </div>
            </div>

            {/* Posts List */}
            <div style={{ maxHeight: '500px', overflow: 'auto' }}>
              {fallbackPostsModal.posts.map((post, index) => (
                <div key={post.post_id} style={{
                  background: 'rgba(255, 165, 0, 0.05)',
                  border: '1px solid rgba(255, 165, 0, 0.2)',
                  borderRadius: '8px',
                  padding: '15px',
                  marginBottom: '10px',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease'
                }}
                onClick={() => {
                  const isSelected = fallbackPostsModal.selectedPosts.includes(post.post_id)
                  if (isSelected) {
                    setFallbackPostsModal(prev => ({
                      ...prev,
                      selectedPosts: prev.selectedPosts.filter(id => id !== post.post_id)
                    }))
                  } else {
                    setFallbackPostsModal(prev => ({
                      ...prev,
                      selectedPosts: [...prev.selectedPosts, post.post_id]
                    }))
                  }
                }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '15px' }}>
                    <input
                      type="checkbox"
                      checked={fallbackPostsModal.selectedPosts.includes(post.post_id)}
                      onChange={() => {}} // Handled by div onClick
                      style={{
                        marginTop: '5px',
                        accentColor: '#ffa500'
                      }}
                    />

                    <div style={{ flex: 1 }}>
                      <div style={{
                        color: '#ffffff',
                        fontSize: '1.1em',
                        fontWeight: 'bold',
                        marginBottom: '8px'
                      }}>
                        {post.title}
                      </div>

                      <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                        gap: '10px',
                        color: '#8892b0',
                        fontSize: '0.9em'
                      }}>
                        <div>👤 u/{post.author}</div>
                        <div>📊 Stage: {post.current_stage}</div>
                        <div>⚡ Fallback: {post.fallback_stage}</div>
                        <div>🔢 Retries: {post.retry_count || 0}</div>
                      </div>

                      <div style={{
                        marginTop: '8px',
                        padding: '8px',
                        background: 'rgba(0, 0, 0, 0.2)',
                        borderRadius: '5px',
                        fontSize: '0.85em',
                        color: '#ff9999'
                      }}>
                        <strong>Reason:</strong> {post.reason}
                      </div>

                      {post.fallback_time && (
                        <div style={{
                          marginTop: '5px',
                          fontSize: '0.8em',
                          color: '#8892b0'
                        }}>
                          Fallback occurred: {new Date(post.fallback_time).toLocaleString()}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}

              {fallbackPostsModal.posts.length === 0 && (
                <div style={{
                  textAlign: 'center',
                  color: '#8892b0',
                  fontSize: '1.1em',
                  padding: '40px'
                }}>
                  No fallback events found
                </div>
              )}
            </div>

            <div style={{
              marginTop: '25px',
              textAlign: 'center'
            }}>
              <button
                onClick={() => setFallbackPostsModal({visible: false, posts: [], selectedPosts: [], timeoutMinutes: 30})}
                style={{
                  background: 'linear-gradient(45deg, #ffa500, #ff8c00)',
                  border: 'none',
                  borderRadius: '10px',
                  color: '#ffffff',
                  padding: '12px 30px',
                  fontSize: '1em',
                  fontWeight: 'bold',
                  cursor: 'pointer'
                }}
              >
                CLOSE
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Post Review Modal */}
      {postModal.visible && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.8)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000
        }}>
          <div style={{
            background: 'linear-gradient(135deg, #0f0f23 0%, #1a1a3a 50%, #0f0f23 100%)',
            border: '2px solid #ff006e',
            borderRadius: '15px',
            padding: '30px',
            maxWidth: '90%',
            maxHeight: '90%',
            overflow: 'auto',
            minWidth: '800px',
            boxShadow: '0 0 50px rgba(255, 0, 110, 0.3)'
          }}>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '25px'
            }}>
              <h2 style={{
                color: '#ff006e',
                fontSize: '1.8em',
                textTransform: 'uppercase',
                textShadow: '0 0 10px #ff006e',
                margin: 0
              }}>
                📝 POST REVIEW & SUBMISSION
              </h2>
              <button
                onClick={() => setPostModal({ visible: false, post: null, originalPost: '', editableResponse: '', suspended: false, posting: false })}
                style={{
                  background: 'transparent',
                  border: '2px solid #ff006e',
                  borderRadius: '50%',
                  width: '40px',
                  height: '40px',
                  color: '#ff006e',
                  fontSize: '20px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
              >
                ×
              </button>
            </div>

            <div style={{ display: 'flex', gap: '20px', marginBottom: '20px' }}>
              {/* Original Post */}
              <div style={{ flex: 1 }}>
                <h3 style={{
                  color: '#3a86ff',
                  fontSize: '1.2em',
                  marginBottom: '10px',
                  textShadow: '0 0 10px #3a86ff'
                }}>
                  📄 Original Post
                </h3>
                <textarea
                  value={postModal.originalPost}
                  readOnly
                  style={{
                    width: '100%',
                    height: '300px',
                    background: 'rgba(255, 255, 255, 0.05)',
                    border: '1px solid rgba(58, 134, 255, 0.3)',
                    borderRadius: '8px',
                    padding: '15px',
                    color: '#ffffff',
                    fontSize: '0.9em',
                    lineHeight: '1.5',
                    resize: 'none',
                    fontFamily: 'inherit'
                  }}
                />
              </div>

              {/* Editable Response */}
              <div style={{ flex: 1 }}>
                <h3 style={{
                  color: '#ff006e',
                  fontSize: '1.2em',
                  marginBottom: '10px',
                  textShadow: '0 0 10px #ff006e'
                }}>
                  ✏️ Response (Editable)
                </h3>
                <textarea
                  value={postModal.editableResponse}
                  onChange={(e) => setPostModal(prev => ({ ...prev, editableResponse: e.target.value }))}
                  style={{
                    width: '100%',
                    height: '300px',
                    background: 'rgba(255, 255, 255, 0.05)',
                    border: '1px solid rgba(255, 0, 110, 0.3)',
                    borderRadius: '8px',
                    padding: '15px',
                    color: '#ffffff',
                    fontSize: '0.9em',
                    lineHeight: '1.5',
                    resize: 'none',
                    fontFamily: 'inherit'
                  }}
                />
              </div>
            </div>

            {/* Controls */}
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginTop: '20px'
            }}>
              <label style={{
                display: 'flex',
                alignItems: 'center',
                color: '#ffffff',
                fontSize: '1em',
                cursor: 'pointer'
              }}>
                <input
                  type="checkbox"
                  checked={postModal.suspended}
                  onChange={(e) => setPostModal(prev => ({ ...prev, suspended: e.target.checked }))}
                  style={{
                    marginRight: '8px',
                    transform: 'scale(1.2)'
                  }}
                />
                🚫 Suspend (don't post)
              </label>

              <div style={{ display: 'flex', gap: '15px' }}>
                <button
                  onClick={() => setPostModal({ visible: false, post: null, originalPost: '', editableResponse: '', suspended: false, posting: false })}
                  style={{
                    ...synthwaveStyles.button,
                    background: 'linear-gradient(45deg, #8892b0, #64748b)',
                    padding: '12px 24px'
                  }}
                  className="synthwave-button"
                >
                  CANCEL
                </button>
                <button
                  onClick={postToReddit}
                  disabled={postModal.suspended || postModal.posting}
                  style={{
                    ...synthwaveStyles.button,
                    background: postModal.suspended
                      ? 'linear-gradient(45deg, #64748b, #475569)'
                      : 'linear-gradient(45deg, #ff006e, #8338ec)',
                    padding: '12px 24px',
                    opacity: postModal.suspended ? 0.5 : 1,
                    cursor: postModal.suspended ? 'not-allowed' : 'pointer'
                  }}
                  className="synthwave-button"
                >
                  {postModal.posting ? '⏳ POSTING...' : '🚀 ACCEPT & POST TO REDDIT'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App