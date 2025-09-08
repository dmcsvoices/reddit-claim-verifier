import { useState, useEffect } from 'react'

const API_BASE = 'http://localhost:5151'

function App() {
  const [health, setHealth] = useState<any>(null)
  const [posts, setPosts] = useState<any[]>([])
  const [subreddit, setSubreddit] = useState('')
  const [hours, setHours] = useState(4)
  const [scanning, setScanning] = useState(false)
  const [scanResult, setScanResult] = useState<any>(null)

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