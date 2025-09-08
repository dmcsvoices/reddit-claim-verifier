import { useState, useEffect } from 'react'

const API_BASE = 'http://localhost:5151'

function App() {
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
  const [showQueueDashboard, setShowQueueDashboard] = useState(false)
  
  // Agent Management state
  const [agentPrompts, setAgentPrompts] = useState<any[]>([])
  const [agentConfig, setAgentConfig] = useState<any>(null)
  const [showAgentManager, setShowAgentManager] = useState(false)
  const [editingPrompt, setEditingPrompt] = useState<any>(null)

  const checkHealth = async () => {
    try {
      const response = await fetch(`${API_BASE}/health`)
      const data = await response.json()
      setHealth(data)
    } catch (error) {
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
      getPosts() // Refresh posts after scan
    } catch (error) {
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
      
      // Show success message and remind user to wait
      if (data.restart_required) {
        setCredentialsResult({ 
          ...data, 
          message: data.message + ' Please wait a moment for the backend to reload the new credentials...'
        })
        
        // Check health status after a delay to see if credentials are working
        setTimeout(() => {
          checkHealth()
        }, 3000)
      }
      
    } catch (error) {
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
        const result = await response.json()
        console.log(`Queue ${stage} paused:`, result)
        getQueueStatus() // Refresh status only
      }
    } catch (error) {
      console.error(`Failed to pause ${stage}:`, error)
    }
  }

  const resumeQueue = async (stage: string) => {
    try {
      const response = await fetch(`${API_BASE}/queue/resume/${stage}`, { method: 'POST' })
      if (response.ok) {
        const result = await response.json()
        console.log(`Queue ${stage} resumed:`, result)
        getQueueStatus() // Refresh status only
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
        getAgentPrompts() // Refresh prompts
        setEditingPrompt(null)
      }
    } catch (error) {
      console.error('Failed to update agent prompt:', error)
    }
  }

  useEffect(() => {
    checkHealth()
    getPosts()
  }, [])

  return (
    <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif' }}>
      <h1>Reddit Claim Verifier</h1>
      
      <div style={{ marginBottom: '20px' }}>
        <h2>Health Check</h2>
        <button onClick={checkHealth}>Check Health</button>
        {health && (
          <pre style={{ background: '#f0f0f0', padding: '10px', marginTop: '10px' }}>
            {JSON.stringify(health, null, 2)}
          </pre>
        )}
      </div>



      <div style={{ marginBottom: '20px' }}>
        <h2>Reddit Scanner</h2>
        <div style={{ marginBottom: '10px' }}>
          <input
            type="text"
            placeholder="Enter subreddit name (e.g., Python)"
            value={subreddit}
            onChange={(e) => setSubreddit(e.target.value)}
            style={{ padding: '8px', marginRight: '10px', width: '200px' }}
          />
          <input
            type="number"
            placeholder="Hours"
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            min="1"
            max="24"
            style={{ padding: '8px', marginRight: '10px', width: '80px' }}
          />
          <button 
            onClick={scanSubreddit} 
            disabled={scanning}
            style={{ padding: '8px 16px' }}
          >
            {scanning ? 'Scanning...' : 'Scan'}
          </button>
        </div>
        
        {scanResult && (
          <div style={{ background: scanResult.error ? '#ffebee' : '#e8f5e8', padding: '10px', marginTop: '10px', borderRadius: '4px' }}>
            {scanResult.error ? (
              <p style={{ color: 'red' }}><strong>Error:</strong> {scanResult.error}</p>
            ) : (
              <div>
                <p><strong>Subreddit:</strong> r/{scanResult.subreddit}</p>
                <p><strong>Time Window:</strong> {scanResult.hours} hours</p>
                <p><strong>Posts Found:</strong> {scanResult.found}</p>
                <p><strong>New Posts Saved:</strong> {scanResult.saved}</p>
                {scanResult.sample && scanResult.sample.length > 0 && (
                  <div>
                    <p><strong>Sample Posts:</strong></p>
                    {scanResult.sample.map((post, index) => (
                      <div key={index} style={{ border: '1px solid #ddd', padding: '8px', margin: '4px 0', background: 'white' }}>
                        <p><strong>{post.title}</strong></p>
                        <p>by u/{post.author} • {new Date(post.created_utc).toLocaleString()}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <div style={{ marginBottom: '20px' }}>
        <h2>Reddit Credentials</h2>
        <button 
          onClick={() => setShowCredentials(!showCredentials)}
          style={{ padding: '8px 16px', marginBottom: '10px' }}
        >
          {showCredentials ? 'Hide Credentials' : 'Update Credentials'}
        </button>
        
        {showCredentials && (
          <div style={{ border: '1px solid #ddd', padding: '15px', borderRadius: '4px', background: '#f9f9f9' }}>
            <div style={{ marginBottom: '10px' }}>
              <label style={{ display: 'block', marginBottom: '5px' }}>Reddit Client ID:</label>
              <input
                type="text"
                value={credentials.reddit_client_id}
                onChange={(e) => setCredentials({ ...credentials, reddit_client_id: e.target.value })}
                placeholder="Your Reddit app client ID"
                style={{ width: '100%', padding: '8px', marginBottom: '10px' }}
              />
            </div>
            
            <div style={{ marginBottom: '10px' }}>
              <label style={{ display: 'block', marginBottom: '5px' }}>Reddit Client Secret:</label>
              <input
                type="password"
                value={credentials.reddit_client_secret}
                onChange={(e) => setCredentials({ ...credentials, reddit_client_secret: e.target.value })}
                placeholder="Your Reddit app client secret"
                style={{ width: '100%', padding: '8px', marginBottom: '10px' }}
              />
            </div>
            
            <div style={{ marginBottom: '10px' }}>
              <label style={{ display: 'block', marginBottom: '5px' }}>Reddit Username:</label>
              <input
                type="text"
                value={credentials.reddit_username}
                onChange={(e) => setCredentials({ ...credentials, reddit_username: e.target.value })}
                placeholder="Your Reddit username"
                style={{ width: '100%', padding: '8px', marginBottom: '10px' }}
              />
            </div>
            
            <div style={{ marginBottom: '10px' }}>
              <label style={{ display: 'block', marginBottom: '5px' }}>Reddit Password:</label>
              <input
                type="password"
                value={credentials.reddit_password}
                onChange={(e) => setCredentials({ ...credentials, reddit_password: e.target.value })}
                placeholder="Your Reddit password (or app password if 2FA enabled)"
                style={{ width: '100%', padding: '8px', marginBottom: '10px' }}
              />
            </div>
            
            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px' }}>User Agent:</label>
              <input
                type="text"
                value={credentials.reddit_user_agent}
                onChange={(e) => setCredentials({ ...credentials, reddit_user_agent: e.target.value })}
                style={{ width: '100%', padding: '8px', marginBottom: '10px' }}
              />
            </div>
            
            <button 
              onClick={updateCredentials} 
              disabled={credentialsUpdating}
              style={{ 
                padding: '10px 20px', 
                background: '#007bff', 
                color: 'white', 
                border: 'none', 
                borderRadius: '4px',
                cursor: credentialsUpdating ? 'not-allowed' : 'pointer',
                opacity: credentialsUpdating ? 0.6 : 1
              }}
            >
              {credentialsUpdating ? 'Updating...' : 'Update & Restart Backend'}
            </button>
            
            {credentialsResult && (
              <div style={{ 
                background: credentialsResult.error ? '#ffebee' : '#e8f5e8', 
                padding: '10px', 
                marginTop: '10px', 
                borderRadius: '4px' 
              }}>
                {credentialsResult.error ? (
                  <p style={{ color: 'red', margin: 0 }}>
                    <strong>Error:</strong> {credentialsResult.error}
                  </p>
                ) : (
                  <p style={{ color: 'green', margin: 0 }}>
                    <strong>Success:</strong> {credentialsResult.message}
                  </p>
                )}
              </div>
            )}
            
            <div style={{ marginTop: '15px', fontSize: '0.9em', color: '#666' }}>
              <p><strong>Note:</strong> You can get Reddit API credentials from <a href="https://www.reddit.com/prefs/apps" target="_blank">reddit.com/prefs/apps</a></p>
              <p>Create a "script" type application and use the Client ID and Client Secret.</p>
            </div>
          </div>
        )}
      </div>

      <div style={{ marginBottom: '20px' }}>
        <h2>Queue Management Dashboard</h2>
        <button 
          onClick={() => {
            setShowQueueDashboard(!showQueueDashboard)
            if (!showQueueDashboard) {
              getQueueStatus()
              getQueueStats()
            }
          }}
          style={{ padding: '8px 16px', marginBottom: '10px' }}
        >
          {showQueueDashboard ? 'Hide Queue Dashboard' : 'Show Queue Dashboard'}
        </button>
        
        {showQueueDashboard && (
          <div style={{ border: '1px solid #ddd', padding: '15px', borderRadius: '4px', background: '#f9f9f9' }}>
            
            {/* Queue Status */}
            {queueStatus && (
              <div style={{ marginBottom: '20px' }}>
                <h3>Queue Status</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px' }}>
                  {Object.entries(queueStatus.endpoint_status || {}).map(([stage, status]: [string, any]) => (
                    <div key={stage} style={{ 
                      border: '1px solid #ccc', 
                      padding: '10px', 
                      borderRadius: '4px',
                      background: status.available ? '#e8f5e8' : '#ffebee'
                    }}>
                      <h4>{stage.charAt(0).toUpperCase() + stage.slice(1)}</h4>
                      <p>Status: {status.available ? '🟢 Online' : '🔴 Offline'}</p>
                      <p>Load: {status.current_load}/{status.max_concurrent}</p>
                      <div style={{ marginTop: '10px' }}>
                        <button 
                          onClick={() => pauseQueue(stage)}
                          style={{ marginRight: '5px', padding: '5px 10px', background: '#ff6b6b', color: 'white', border: 'none', borderRadius: '3px' }}
                        >
                          Pause
                        </button>
                        <button 
                          onClick={() => resumeQueue(stage)}
                          style={{ padding: '5px 10px', background: '#51cf66', color: 'white', border: 'none', borderRadius: '3px' }}
                        >
                          Resume
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {/* Queue Statistics */}
            {queueStats && (
              <div style={{ marginBottom: '20px' }}>
                <h3>Queue Statistics</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '10px' }}>
                  {queueStats.detailed_stats?.map((stat: any, index: number) => (
                    <div key={index} style={{ border: '1px solid #ccc', padding: '10px', borderRadius: '4px' }}>
                      <h4>{stat.stage} - {stat.status}</h4>
                      <p>Count: {stat.count}</p>
                      <p>Avg Retries: {stat.avg_retries?.toFixed(2) || 0}</p>
                      {stat.oldest_post && <p>Oldest: {new Date(stat.oldest_post).toLocaleString()}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            <button 
              onClick={() => { getQueueStatus(); getQueueStats(); }}
              style={{ padding: '10px 20px', background: '#007bff', color: 'white', border: 'none', borderRadius: '4px' }}
            >
              Refresh Dashboard
            </button>
          </div>
        )}
      </div>

      <div style={{ marginBottom: '20px' }}>
        <h2>Agent Management</h2>
        <button 
          onClick={() => {
            setShowAgentManager(!showAgentManager)
            if (!showAgentManager) {
              getAgentPrompts()
              getAgentConfig()
            }
          }}
          style={{ padding: '8px 16px', marginBottom: '10px' }}
        >
          {showAgentManager ? 'Hide Agent Manager' : 'Show Agent Manager'}
        </button>
        
        {showAgentManager && (
          <div style={{ border: '1px solid #ddd', padding: '15px', borderRadius: '4px', background: '#f9f9f9' }}>
            
            {/* Agent Configuration Overview */}
            {agentConfig && (
              <div style={{ marginBottom: '20px' }}>
                <h3>Agent Configuration</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '10px' }}>
                  {Object.entries(agentConfig.config || {}).map(([stage, config]: [string, any]) => (
                    <div key={stage} style={{ border: '1px solid #ccc', padding: '10px', borderRadius: '4px', background: 'white' }}>
                      <h4>{stage.charAt(0).toUpperCase() + stage.slice(1)}</h4>
                      <p><strong>Model:</strong> {config.model}</p>
                      <p><strong>Endpoint:</strong> {config.endpoint}</p>
                      <p><strong>Max Concurrent:</strong> {config.max_concurrent}</p>
                      <p><strong>Description:</strong> {config.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {/* System Prompts Management */}
            <div>
              <h3>System Prompts</h3>
              {agentPrompts.map((prompt, index) => (
                <div key={index} style={{ marginBottom: '15px', padding: '10px', background: '#fff', borderRadius: '4px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                    <h4>{prompt.agent_stage.charAt(0).toUpperCase() + prompt.agent_stage.slice(1)} Agent (v{prompt.version})</h4>
                    <button 
                      onClick={() => setEditingPrompt(prompt)}
                      style={{ padding: '4px 8px', fontSize: '12px' }}
                    >
                      Edit
                    </button>
                  </div>
                  
                  {editingPrompt?.agent_stage === prompt.agent_stage ? (
                    <div>
                      <textarea
                        value={editingPrompt.system_prompt}
                        onChange={(e) => setEditingPrompt({ ...editingPrompt, system_prompt: e.target.value })}
                        style={{ width: '100%', minHeight: '100px', padding: '10px', marginBottom: '10px' }}
                      />
                      <button 
                        onClick={() => updateAgentPrompt(editingPrompt.agent_stage, editingPrompt.system_prompt)}
                        style={{ marginRight: '10px', padding: '8px 16px', background: '#28a745', color: 'white', border: 'none', borderRadius: '4px' }}
                      >
                        Save
                      </button>
                      <button 
                        onClick={() => setEditingPrompt(null)}
                        style={{ padding: '8px 16px', background: '#6c757d', color: 'white', border: 'none', borderRadius: '4px' }}
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <div style={{ 
                      background: '#f8f9fa', 
                      padding: '10px', 
                      borderRadius: '3px',
                      fontFamily: 'monospace',
                      fontSize: '0.9em',
                      maxHeight: '100px',
                      overflow: 'auto'
                    }}>
                      {prompt.system_prompt || 'No system prompt configured'}
                    </div>
                  )}
                </div>
              ))}
            </div>
            
            <button 
              onClick={() => { getAgentPrompts(); getAgentConfig(); }}
              style={{ padding: '10px 20px', background: '#007bff', color: 'white', border: 'none', borderRadius: '4px' }}
            >
              Refresh Agent Data
            </button>
          </div>
        )}
      </div>

      <div style={{ marginBottom: '20px' }}>
        <h2>Posts</h2>
        <button onClick={getPosts}>Get Posts</button>
        <button onClick={insertDummy} style={{ marginLeft: '10px' }}>Insert Dummy</button>
        <div style={{ marginTop: '10px' }}>
          {posts.length === 0 ? (
            <p>No posts found</p>
          ) : (
            posts.map((post, index) => (
              <div key={index} style={{ border: '1px solid #ccc', padding: '10px', margin: '5px 0' }}>
                <p><strong>Title:</strong> {post[2]}</p>
                <p><strong>Author:</strong> {post[3]}</p>
                <p><strong>URL:</strong> {post[5]}</p>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

export default App