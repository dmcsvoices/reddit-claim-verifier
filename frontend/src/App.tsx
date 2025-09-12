import { useState, useEffect } from 'react'
import './synthwave.css'

const API_BASE = 'http://localhost:5151'

type TabType = 'monitoring' | 'queues' | 'agents'

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
  
  // Agent Backend state  
  const [availableModels, setAvailableModels] = useState<{[key: string]: string[]}>({}) 
  
  // Agent Management state
  const [agentPrompts, setAgentPrompts] = useState<any[]>([])
  const [agentConfig, setAgentConfig] = useState<any>(null)
  const [editingPrompt, setEditingPrompt] = useState<any>(null)
  const [testingEndpoint, setTestingEndpoint] = useState<string | null>(null)
  const [currentEndpoints, setCurrentEndpoints] = useState<{[key: string]: string}>({}) // Track current endpoint values per stage
  const [currentModels, setCurrentModels] = useState<{[key: string]: string}>({}) // Track current model selections per stage

  // Database persistence helpers
  const saveAgentSettings = async () => {
    try {
      // Save each agent configuration to database
      for (const stage of Object.keys(currentEndpoints)) {
        if (currentModels[stage] && currentEndpoints[stage]) {
          await fetch(`${API_BASE}/agents/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              agent_stage: stage,
              model: currentModels[stage],
              endpoint: currentEndpoints[stage],
              timeout: 120,
              max_concurrent: 2
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
          
          for (const [stage, config] of Object.entries(data.config)) {
            const stageConfig = config as any
            endpoints[stage] = stageConfig.endpoint
            models[stage] = stageConfig.model
          }
          
          setCurrentEndpoints(endpoints)
          setCurrentModels(models)
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
    }
    initializeData()
  }, [])

  // Auto-save when settings change
  useEffect(() => {
    if (Object.keys(currentEndpoints).length > 0 || Object.keys(currentModels).length > 0) {
      saveAgentSettings()
    }
  }, [currentEndpoints, currentModels])

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
          style={synthwaveStyles.navButton(activeTab === 'agents')}
          onClick={() => {
            setActiveTab('agents')
            getAgentPrompts()
            getAgentConfig()
          }}
          className="synthwave-button"
        >
          🧠 Agent Config
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
          <button style={synthwaveStyles.button} onClick={checkHealth} className="synthwave-button">
            REFRESH STATUS
          </button>
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
              <div style={{ display: 'flex', gap: '15px', marginBottom: '20px' }}>
                <button onClick={getPosts} style={synthwaveStyles.button} className="synthwave-button">
                  🔄 REFRESH POSTS
                </button>
                <button onClick={insertDummy} style={synthwaveStyles.button} className="synthwave-button">
                  ➕ INSERT TEST POST
                </button>
              </div>
              
              <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
                {posts.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '40px', color: '#8338ec' }}>
                    <div style={{ fontSize: '3em', marginBottom: '10px' }}>📭</div>
                    <div>No posts found in database</div>
                  </div>
                ) : (
                  posts.map((post, index) => (
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
                  ))
                )}
              </div>
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
              
              <button 
                onClick={() => { getQueueStatus(); getQueueStats(); }}
                style={{
                  ...synthwaveStyles.button,
                  marginTop: '20px',
                  background: 'linear-gradient(45deg, #8338ec, #3a86ff)'
                }}
                className="synthwave-button"
              >
                🔄 REFRESH DASHBOARD
              </button>
            </div>
            
            {/* Queue Statistics */}
            {queueStats && (
              <div style={synthwaveStyles.card} className="synthwave-card">
                <h2 style={synthwaveStyles.cardTitle}>📊 QUEUE STATISTICS</h2>
                <div style={synthwaveStyles.grid}>
                  {queueStats.detailed_stats?.map((stat: any, index: number) => (
                    <div key={index} style={{
                      background: 'rgba(131, 56, 236, 0.1)',
                      border: '1px solid rgba(131, 56, 236, 0.3)',
                      borderRadius: '10px',
                      padding: '20px'
                    }}>
                      <h4 style={{ color: '#8338ec', marginBottom: '15px', textTransform: 'uppercase' }}>
                        {stat.stage} - {stat.status}
                      </h4>
                      
                      <div style={{ display: 'grid', gap: '10px' }}>
                        <div>
                          <span style={{ color: '#ff006e' }}>Count:</span>
                          <span style={{ color: '#ffffff', marginLeft: '10px', fontSize: '1.2em' }}>{stat.count}</span>
                        </div>
                        <div>
                          <span style={{ color: '#ff006e' }}>Avg Retries:</span>
                          <span style={{ color: '#ffffff', marginLeft: '10px' }}>{stat.avg_retries?.toFixed(2) || 0}</span>
                        </div>
                        {stat.oldest_post && (
                          <div>
                            <span style={{ color: '#ff006e' }}>Oldest:</span>
                            <div style={{ color: '#3a86ff', fontSize: '0.9em', marginTop: '5px' }}>
                              {new Date(stat.oldest_post).toLocaleString()}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
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
                          <label style={{ display: 'block', marginBottom: '5px', color: '#ff006e', fontSize: '0.9em' }}>Endpoint URL:</label>
                          <input
                            id={`endpoint-${stage}`}
                            type="text"
                            defaultValue={currentEndpoints[stage] || config.endpoint}
                            key={`${stage}-${currentEndpoints[stage] || config.endpoint}`} // Force re-render when endpoint changes
                            placeholder="http://localhost:11434 (base URL only, /v1/models will be auto-appended)"
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
                                // Update the current endpoint for this stage
                                setCurrentEndpoints(prev => ({ ...prev, [stage]: url }))
                                // Silently fetch models when endpoint changes
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

                        {/* Model Selection */}
                        <div>
                          <label style={{ display: 'block', marginBottom: '5px', color: '#ff006e', fontSize: '0.9em' }}>Selected Model:</label>
                          <select
                            defaultValue={currentModels[stage] || config.model}
                            key={`model-${stage}-${currentModels[stage] || config.model}`} // Force re-render when model changes
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
                            {availableModels[currentEndpoints[stage] || config.endpoint]?.map((model: string, idx: number) => {
                              const currentModel = currentModels[stage] || config.model
                              return model !== currentModel && (
                                <option key={idx} value={model}>{model}</option>
                              )
                            })}
                          </select>
                          {(() => {
                            const currentEndpoint = currentEndpoints[stage] || config.endpoint
                            return availableModels[currentEndpoint] ? (
                              <div style={{ color: '#8338ec', fontSize: '0.8em', marginTop: '5px' }}>
                                ✅ {availableModels[currentEndpoint].length} models available
                                <br />
                                <small style={{ color: '#666', fontSize: '0.7em' }}>
                                  Cache key: {currentEndpoint}
                                  <br />
                                  All keys: {Object.keys(availableModels).join(', ')}
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
              {agentPrompts.map((prompt, index) => (
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
              ))}
              
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
      </div>
    </div>
  )
}

export default App