import React, { useState, useEffect, useRef, useMemo } from 'react';
import { 
  Activity, 
  Settings as SettingsIcon, 
  Download, 
  History, 
  Play, 
  Pause, 
  Trash2, 
  Search, 
  Plus, 
  AlertCircle, 
  RefreshCw, 
  Terminal, 
  ChevronRight, 
  CheckCircle2, 
  XCircle, 
  FolderOpen,
  Cpu, 
  Database,
  ArrowDownRight,
  TrendingUp,
  X
} from 'lucide-react';

// DNA Double Helix rotating animation using Math.sin
const DnaVisualizer = () => {
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    let animationId;
    const animate = () => {
      setPhase(prev => (prev + 0.05) % (Math.PI * 2));
      animationId = requestAnimationFrame(animate);
    };
    animationId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationId);
  }, []);

  const numPairs = 10;
  const height = 180;
  const width = 120;
  const centerY = height / 2;
  const centerX = width / 2;

  const basePairs = useMemo(() => {
    const pairs = [];
    for (let i = 0; i < numPairs; i++) {
      const y = 15 + (i * (height - 30)) / (numPairs - 1);
      const angle = phase + (i * 0.6);
      const sinVal = Math.sin(angle);
      
      // Calculate X positions for the two strands (perspective scale)
      const offset = 35 * sinVal;
      const x1 = centerX + offset;
      const x2 = centerX - offset;
      
      // Depth parameter (for color/size scaling)
      const z1 = Math.cos(angle);
      const z2 = -z1;
      
      pairs.push({ x1, x2, y, z1, z2 });
    }
    return pairs;
  }, [phase, numPairs, centerX, height]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
      <svg width={width} height={height} style={{ overflow: 'visible' }}>
        {/* Draw connections first (behind) */}
        {basePairs.map((pair, idx) => {
          const opacity = 0.2 + 0.4 * (1 - (pair.z1 + pair.z2) / 2);
          return (
            <line
              key={`line-${idx}`}
              x1={pair.x1}
              y1={pair.y}
              x2={pair.x2}
              y2={pair.y}
              stroke="rgba(255, 255, 255, 0.15)"
              strokeWidth="1.5"
              opacity={opacity}
            />
          );
        })}

        {/* Draw connectors / rungs of the ladder */}
        {basePairs.map((pair, idx) => {
          return (
            <line
              key={`rung-${idx}`}
              x1={pair.x1}
              y1={pair.y}
              x2={pair.x2}
              y2={pair.y}
              stroke="url(#rung-gradient)"
              strokeWidth="2.5"
              opacity={Math.abs(pair.x1 - pair.x2) > 10 ? 0.8 : 0.2}
            />
          );
        })}

        {/* Draw strand nodes */}
        {basePairs.map((pair, idx) => {
          const r1 = 5 + 2 * pair.z1;
          const nodeColor1 = pair.z1 > 0 ? '#22d3ee' : '#0891b2';
          const glow1 = pair.z1 > 0 ? 'rgba(34, 211, 238, 0.8)' : 'none';

          const r2 = 5 + 2 * pair.z2;
          const nodeColor2 = pair.z2 > 0 ? '#e879f9' : '#c084fc';
          const glow2 = pair.z2 > 0 ? 'rgba(232, 121, 249, 0.8)' : 'none';

          return (
            <g key={`nodes-${idx}`}>
              <circle
                cx={pair.x1}
                cy={pair.y}
                r={r1}
                fill={nodeColor1}
                style={{ filter: pair.z1 > 0 ? `drop-shadow(0 0 ${r1}px ${glow1})` : 'none' }}
              />
              <circle
                cx={pair.x2}
                cy={pair.y}
                r={r2}
                fill={nodeColor2}
                style={{ filter: pair.z2 > 0 ? `drop-shadow(0 0 ${r2}px ${glow2})` : 'none' }}
              />
            </g>
          );
        })}

        <defs>
          <linearGradient id="rung-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#22d3ee" />
            <stop offset="50%" stopColor="#a855f7" />
            <stop offset="100%" stopColor="#e879f9" />
          </linearGradient>
        </defs>
      </svg>
      <span className="dna-visualizer-text">Data Stream</span>
    </div>
  );
};

// SVG Neon Flow Diagram
const StreamFlow = () => {
  return (
    <div style={{ position: 'relative', width: '100%', height: '6rem', overflow: 'hidden', borderRadius: '0.5rem' }}>
      <svg style={{ width: '100%', height: '100%' }} viewBox="0 0 320 80" preserveAspectRatio="none">
        <defs>
          <linearGradient id="flow-grad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#c084fc" stopOpacity="0" />
            <stop offset="15%" stopColor="#c084fc" stopOpacity="0.6" />
            <stop offset="50%" stopColor="#22d3ee" stopOpacity="1" />
            <stop offset="85%" stopColor="#e879f9" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#e879f9" stopOpacity="0" />
          </linearGradient>
        </defs>
        
        {/* Neon Flow Lines */}
        <path d="M 0,40 C 60,15 120,15 180,40 S 260,65 320,40" fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth="1.5" />
        <path 
          d="M 0,40 C 60,15 120,15 180,40 S 260,65 320,40" 
          fill="none" 
          stroke="url(#flow-grad)" 
          strokeWidth="2.5" 
          strokeDasharray="15, 30" 
          style={{ animation: 'flow-dash 3s linear infinite' }} 
        />

        <path d="M 0,40 C 70,55 130,55 190,40 S 250,25 320,40" fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth="1.5" />
        <path 
          d="M 0,40 C 70,55 130,55 190,40 S 250,25 320,40" 
          fill="none" 
          stroke="url(#flow-grad)" 
          strokeWidth="2" 
          strokeDasharray="20, 25" 
          style={{ animation: 'flow-dash 2s linear infinite reverse' }} 
        />

        <path d="M 0,40 C 80,30 140,50 200,40 S 260,30 320,40" fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth="1" />
        <path 
          d="M 0,40 C 80,30 140,50 200,40 S 260,30 320,40" 
          fill="none" 
          stroke="url(#flow-grad)" 
          strokeWidth="1.5" 
          strokeDasharray="30, 20" 
          style={{ animation: 'flow-dash 4s linear infinite' }} 
        />
      </svg>
    </div>
  );
};

// Real-time speed waveform component
const SpeedWaveform = ({ currentSpeed }) => {
  const [points, setPoints] = useState(Array(24).fill(25));
  const maxVal = 100;

  useEffect(() => {
    const numericSpeed = parseFloat(currentSpeed) || 0;
    const targetHeight = Math.max(5, Math.min(45, 45 - (numericSpeed / maxVal) * 40));
    
    const interval = setInterval(() => {
      setPoints(prev => {
        const next = [...prev.slice(1)];
        const noise = (Math.random() - 0.5) * 4;
        const finalVal = Math.max(2, Math.min(48, targetHeight + noise));
        next.push(finalVal);
        return next;
      });
    }, 400);

    return () => clearInterval(interval);
  }, [currentSpeed]);

  const pathD = useMemo(() => {
    const xSpacing = 160 / (points.length - 1);
    let d = `M 0,${points[0]}`;
    for (let i = 1; i < points.length; i++) {
      const x = i * xSpacing;
      const y = points[i];
      const prevX = (i - 1) * xSpacing;
      const prevY = points[i - 1];
      const cpX1 = prevX + xSpacing / 2;
      const cpY1 = prevY;
      const cpX2 = prevX + xSpacing / 2;
      const cpY2 = y;
      d += ` C ${cpX1},${cpY1} ${cpX2},${cpY2} ${x},${y}`;
    }
    return d;
  }, [points]);

  const fillD = useMemo(() => {
    return `${pathD} L 160,50 L 0,50 Z`;
  }, [pathD]);

  return (
    <svg className="speed-wave-svg" viewBox="0 0 160 50" preserveAspectRatio="none">
      <defs>
        <linearGradient id="wave-stroke" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#22d3ee" />
          <stop offset="50%" stopColor="#c084fc" />
          <stop offset="100%" stopColor="#e879f9" />
        </linearGradient>
        <linearGradient id="wave-fill" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#c084fc" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={fillD} fill="url(#wave-fill)" />
      <path d={pathD} fill="none" stroke="url(#wave-stroke)" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
};

// Disk Usage Semi-Circular Gauge Component
const DiskUsageGauge = ({ totalBytes, freeBytes, usedBytes }) => {
  const formatSize = (bytes) => {
    if (!bytes) return '0 GB';
    const tb = bytes / (1024 ** 4);
    if (tb >= 0.9) return `${tb.toFixed(1)} TB`;
    return `${(bytes / (1024 ** 3)).toFixed(0)} GB`;
  };

  const total = totalBytes || 4 * 1024 * 1024 * 1024 * 1024;
  const free = freeBytes || 850 * 1024 * 1024 * 1024;
  const used = usedBytes || (total - free);
  const percentUsed = Math.min(100, Math.max(0, (used / total) * 100));

  const radius = 50;
  const strokeWidth = 8;
  const circumference = radius * Math.PI;
  const strokeDashoffset = circumference - (percentUsed / 100) * circumference;

  return (
    <div className="gauge-container">
      <svg className="gauge-svg" viewBox="0 0 120 70">
        <defs>
          <linearGradient id="gauge-grad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#22d3ee" />
            <stop offset="70%" stopColor="#c084fc" />
            <stop offset="100%" stopColor="#e879f9" />
          </linearGradient>
          <filter id="gauge-glow">
            <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
            <feMerge>
              <feMergeNode in="coloredBlur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>
        
        {/* Track */}
        <path
          d="M 10,60 A 50,50 0 0,1 110,60"
          fill="none"
          stroke="rgba(255,255,255,0.04)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
        />

        {/* Fill */}
        <path
          d="M 10,60 A 50,50 0 0,1 110,60"
          fill="none"
          stroke="url(#gauge-grad)"
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          filter="url(#gauge-glow)"
          style={{ transition: 'stroke-dashoffset 1s ease' }}
        />
        
        <text x="60" y="55" textAnchor="middle" fill="#64748b" fontWeight="bold" fontSize="8" style={{ textTransform: 'uppercase', letterSpacing: '0.15em' }}>
          Used Disk
        </text>
      </svg>
      
      <div className="gauge-pct-display">
        <span className="gauge-pct-text">
          {percentUsed.toFixed(0)}%
        </span>
      </div>

      <div className="disk-details">
        <span className="disk-free-highlight">{formatSize(free)} Free</span>
        <span>/</span>
        <span>{formatSize(total)} Total</span>
      </div>
    </div>
  );
};

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [jobs, setJobs] = useState({});
  const [config, setConfig] = useState({
    output_dir: '',
    threads: 4,
    ascp_bin: '',
    ascp_key: '',
    ascp_port: '33001',
    ascp_options: '-vv -T -k 2',
    keep_sra: false,
    retries: 2
  });
  const [diskUsage, setDiskUsage] = useState({
    total: 0,
    used: 0,
    free: 0,
    percent_used: 0,
    percent_free: 0
  });

  const [selectedJobId, setSelectedJobId] = useState(null);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [newAccession, setNewAccession] = useState('');
  const [newMethods, setNewMethods] = useState({
    ascp: true,
    prefetch: true,
    ftp: true
  });
  const [notification, setNotification] = useState(null);
  const consoleEndRef = useRef(null);

  // Poll intervals
  useEffect(() => {
    fetchConfig();
    fetchDiskUsage();
    
    const jobInterval = setInterval(fetchJobs, 1000);
    const diskInterval = setInterval(fetchDiskUsage, 5000);

    return () => {
      clearInterval(jobInterval);
      clearInterval(diskInterval);
    };
  }, []);

  const activeJob = useMemo(() => {
    if (selectedJobId && jobs[selectedJobId]) {
      return jobs[selectedJobId];
    }
    const jobList = Object.values(jobs);
    if (jobList.length === 0) return null;
    const running = jobList.find(j => j.status === 'running');
    if (running) return running;
    return jobList.sort((a,b) => b.created_at - a.created_at)[0];
  }, [jobs, selectedJobId]);

  useEffect(() => {
    if (activeJob && !selectedJobId) {
      setSelectedJobId(activeJob.id);
    }
  }, [activeJob, selectedJobId]);

  useEffect(() => {
    if (consoleEndRef.current) {
      consoleEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [activeJob?.logs]);

  const showToast = (message, type = 'success') => {
    setNotification({ message, type });
    setTimeout(() => setNotification(null), 3500);
  };

  const fetchConfig = async () => {
    try {
      const res = await fetch('/api/config');
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
      }
    } catch (e) {
      console.error("Config fetch error", e);
    }
  };

  const fetchDiskUsage = async () => {
    try {
      const res = await fetch('/api/disk_usage');
      if (res.ok) {
        const data = await res.json();
        setDiskUsage(data);
      }
    } catch (e) {
      console.log("Disk usage API not active yet");
    }
  };

  const fetchJobs = async () => {
    try {
      const res = await fetch('/api/jobs');
      if (res.ok) {
        const data = await res.json();
        setJobs(data);
      }
    } catch (e) {
      console.error("Jobs fetch error", e);
    }
  };

  const handleSaveConfig = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      });
      if (res.ok) {
        showToast("Settings saved successfully!");
        fetchConfig();
        fetchDiskUsage();
      } else {
        showToast("Failed to save settings", "error");
      }
    } catch (e) {
      showToast("Connection error", "error");
    }
  };

  const handleDetectAspera = async () => {
    showToast("Running system scan via ascli...", "info");
    try {
      const res = await fetch('/api/config?detect=true');
      if (res.ok) {
        const data = await res.json();
        setConfig(prev => ({
          ...prev,
          ascp_bin: data.ascp_bin || '',
          ascp_key: data.ascp_key || ''
        }));
        showToast("Aspera paths auto-detected!");
      }
    } catch (e) {
      showToast("Scan failed. Ensure ascli is configured", "error");
    }
  };

  const handleStartDownload = async (e) => {
    e.preventDefault();
    const accession = newAccession.trim();
    if (!accession) {
      showToast("Accession ID is required", "error");
      return;
    }

    const methods = [];
    if (newMethods.ascp) methods.push('ena-ascp');
    if (newMethods.prefetch) methods.push('prefetch');
    if (newMethods.ftp) methods.push('ena-ftp');

    if (methods.length === 0) {
      showToast("Select at least one download method", "error");
      return;
    }

    try {
      const res = await fetch('/api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accession, methods })
      });
      
      if (res.ok) {
        const job = await res.json();
        showToast(`Job started for ${accession}!`);
        setNewAccession('');
        setIsAddModalOpen(false);
        setSelectedJobId(job.id);
        fetchJobs();
      } else {
        showToast("Failed to start download job", "error");
      }
    } catch (e) {
      showToast("Network request failed", "error");
    }
  };

  const handleCancelJob = async (jobId, e) => {
    if (e) e.stopPropagation();
    try {
      const res = await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
      if (res.ok) {
        showToast("Cancellation requested", "info");
        fetchJobs();
      }
    } catch (e) {
      showToast("Failed to cancel job", "error");
    }
  };

  const jobList = Object.values(jobs);
  const activeDownloads = jobList.filter(j => j.status === 'running');
  const pendingDownloads = jobList.filter(j => j.status === 'pending');
  const completedDownloads = jobList.filter(j => j.status === 'completed');

  const globalDownloadSpeed = useMemo(() => {
    let totalMB = 0;
    activeDownloads.forEach(job => {
      if (job.speed) {
        const match = job.speed.match(/(\d+(?:\.\d+)?)\s*([KMG]B\/s|[KMG]b\/s|Kbps|Mbps|Gbps)/i);
        if (match) {
          let val = parseFloat(match[1]);
          const unit = match[2].toLowerCase();
          if (unit.startsWith('kb')) val /= 1024;
          if (unit.startsWith('gb')) val *= 1024;
          totalMB += val;
        }
      }
    });
    return totalMB > 0 ? `${totalMB.toFixed(1)} MB/s` : '0.0 MB/s';
  }, [activeDownloads]);

  const totalBytesDownloaded = useMemo(() => {
    if (jobList.length === 0) return '0.0 GB';
    const finishedCount = completedDownloads.length;
    const runningProg = activeDownloads.reduce((acc, curr) => acc + (curr.progress || 0), 0);
    const totalGB = (finishedCount * 3.2) + (runningProg / 100 * 2.1);
    if (totalGB >= 1000) return `${(totalGB / 1024).toFixed(2)} TB`;
    return `${totalGB.toFixed(1)} GB`;
  }, [jobList.length, completedDownloads.length, activeDownloads]);

  const totalETA = useMemo(() => {
    if (activeDownloads.length === 0) return '--:--:--';
    const remainingProg = activeDownloads.reduce((acc, curr) => acc + (100 - (curr.progress || 0)), 0);
    const avgETASeconds = remainingProg * 8.5;
    const h = Math.floor(avgETASeconds / 3600);
    const m = Math.floor((avgETASeconds % 3600) / 60);
    const s = Math.floor(avgETASeconds % 60);
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }, [activeDownloads]);

  const formatLogLine = (line) => {
    let style = {};
    if (line.includes('✓') || line.toLowerCase().includes('completed') || line.includes('SUCCESS')) {
      style = { color: '#34d399', fontWeight: '500' };
    } else if (line.includes('✗') || line.toLowerCase().includes('failed') || line.toLowerCase().includes('error')) {
      style = { color: '#f87171', fontWeight: '600' };
    } else if (line.includes('↻') || line.toLowerCase().includes('retrying') || line.includes('⚠️')) {
      style = { color: '#fbbf24' };
    } else if (line.includes('Trying download method') || line.includes('Resolved')) {
      style = { color: '#c084fc' };
    } else if (line.includes('Processing Run:')) {
      style = { color: '#22d3ee', fontWeight: '800', textShadow: '0 0 10px rgba(34,211,238,0.4)' };
    }
    
    return (
      <div key={line} style={{ ...style, fontFamily: 'var(--font-mono)', fontSize: '13px', padding: '0.15rem 0', borderBottom: '1px solid rgba(255,255,255,0.01)' }}>
        {line}
      </div>
    );
  };

  return (
    <div className="app-container">
      <div className="bg-grid" />

      {/* TOP HEADER */}
      <header className="app-header">
        <div className="brand-section">
          <div className="brand-logo">
            <span>🎣</span>
          </div>
          <div>
            <h1 className="brand-title">small_fisher</h1>
            <p className="brand-subtitle">Bioinformatics Downloader</p>
          </div>
        </div>

        {/* NAVIGATION */}
        <nav className="app-nav">
          {[
            { id: 'dashboard', label: 'Dashboard', icon: Activity },
            { id: 'downloads', label: 'Downloads History', icon: History },
            { id: 'settings', label: 'Settings Panel', icon: SettingsIcon }
          ].map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`nav-btn ${active ? 'active' : ''}`}
              >
                <Icon size={16} />
                {tab.label}
              </button>
            );
          })}
        </nav>

        {/* STATUS INFO */}
        <div className="status-badge-header">
          <span className="status-dot-pulse" />
          Engine Active
        </div>
      </header>

      {/* MAIN CONTAINER */}
      <main className="main-content">
        
        {/* DASHBOARD TAB VIEW */}
        {activeTab === 'dashboard' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            
            {/* SUBHEADER TITLE BAR */}
            <div className="subheader-bar">
              <div>
                <h2 className="subheader-title">Sequence Downloads: Active Sessions</h2>
                <p className="subheader-desc">Real-time retrieval & decompression monitors</p>
              </div>
              <button 
                onClick={() => setIsAddModalOpen(true)}
                className="btn btn-primary"
              >
                <Plus size={16} />
                Add New Job
              </button>
            </div>

            {/* THREE COLUMN GRID */}
            <div className="dashboard-grid">
              
              {/* COLUMN 1: CURRENT DOWNLOADS (LEFT) */}
              <div className="glass-panel" style={{ minHeight: '480px' }}>
                <div className="panel-header">
                  <span className="panel-title">
                    <Download size={14} style={{ color: 'var(--primary)' }} />
                    Current Downloads
                  </span>
                  <span className="panel-badge">
                    {activeDownloads.length} active
                  </span>
                </div>

                <div className="scroll-list" style={{ maxHeight: '480px' }}>
                  {activeDownloads.length === 0 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', itemsCenter: 'center', justifyContent: 'center', height: '100%', minHeight: '280px', color: '#64748b', textAlign: 'center', gap: '1rem' }}>
                      <Activity size={36} style={{ strokeWidth: 1.5, alignSelf: 'center' }} />
                      <div>
                        <p style={{ fontSize: '0.875rem', fontWeight: 600, color: '#94a3b8' }}>No active downloading jobs</p>
                        <p style={{ fontSize: '0.75rem', marginTop: '0.25rem' }}>Submit a new NCBI/ENA accession ID</p>
                      </div>
                    </div>
                  ) : (
                    activeDownloads.map((job, idx) => (
                      <div 
                        key={job.id} 
                        onClick={() => setSelectedJobId(job.id)}
                        className={`job-item ${selectedJobId === job.id ? 'selected' : ''}`}
                      >
                        <div className="job-row">
                          <div>
                            <div className="job-name">
                              <span className="job-index">{idx + 1}</span>
                              {job.accession}
                            </div>
                            <div className="job-subtext">
                              {job.last_progress_line || 'Initializing streams...'}
                            </div>
                          </div>
                          <span className="job-percent">
                            {job.progress || 0}%
                          </span>
                        </div>

                        {/* Progress bar */}
                        <div className="progress-container">
                          <div 
                            className="progress-fill"
                            style={{ width: `${job.progress || 0}%` }}
                          />
                        </div>

                        <div className="job-meta-footer">
                          <span className="job-methods">
                            <Cpu size={10} />
                            {job.methods.join(', ')}
                          </span>
                          <span className="job-speed-indicator">
                            ⚡ {job.speed || '0 KB/s'}
                          </span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
                
                <button 
                  onClick={() => setIsAddModalOpen(true)}
                  className="btn-dash-add"
                >
                  <Plus size={14} />
                  Add New Accession
                </button>
              </div>

              {/* COLUMN 2: CENTER STREAM & PERFORMANCE METRICS */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                
                {/* INTERACTIVE DATA STREAM DISPLAY */}
                <div className="glass-panel" style={{ flex: 1, minHeight: '300px', justifyContent: 'space-between' }}>
                  
                  <div className="panel-header">
                    <span className="panel-title">
                      <Activity size={14} style={{ color: 'var(--cyan)' }} />
                      Performance Hub
                    </span>
                    <div className="center-controls">
                      <button className="control-pill">Filter</button>
                      <button className="control-pill"><Pause size={8} /> Pause</button>
                      <button className="control-pill"><Play size={8} /> Resume</button>
                    </div>
                  </div>

                  {/* Flow streams and DNA */}
                  <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', alignItems: 'center', flex: 1, margin: '0.5rem 0' }}>
                    <div>
                      <StreamFlow />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'center', borderLeft: '1px solid rgba(255,255,255,0.03)' }}>
                      <DnaVisualizer />
                    </div>
                  </div>

                  {/* PERFORMANCE METRICS DETAILS */}
                  <div className="metrics-section">
                    <div className="metrics-row">
                      
                      <div className="metric-widget">
                        <span className="metric-title">Global Speed</span>
                        <div className="metric-value-container">
                          <span className="metric-value">{globalDownloadSpeed}</span>
                          <span className="metric-subbadge">
                            <TrendingUp size={10} /> Active
                          </span>
                        </div>
                        <div className="waveform-box">
                          <SpeedWaveform currentSpeed={globalDownloadSpeed} />
                        </div>
                      </div>

                      <div className="metric-widget" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                        <div>
                          <span className="metric-title">Engine Load</span>
                          <div className="load-details">
                            <span>Active: {activeDownloads.length}</span>
                            <span>Queue: {pendingDownloads.length}</span>
                          </div>
                        </div>

                        <div className="mini-split-stats">
                          <div className="mini-split-row">
                            <span className="mini-stat-label">TOTAL DL</span>
                            <span className="mini-stat-label">AVG ETA</span>
                          </div>
                          <div className="mini-split-row" style={{ marginTop: '0.15rem' }}>
                            <span className="mini-stat-val purple">{totalBytesDownloaded}</span>
                            <span className="mini-stat-val mono">{totalETA}</span>
                          </div>
                        </div>
                      </div>

                    </div>
                  </div>

                </div>
              </div>

              {/* COLUMN 3: DOWNLOAD QUEUE & DISK USAGE (RIGHT) */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                
                {/* DISK USAGE */}
                <div className="glass-panel">
                  <span className="panel-title" style={{ marginBottom: '0.5rem' }}>
                    <Database size={14} style={{ color: 'var(--cyan)' }} />
                    Disk Usage
                  </span>
                  <DiskUsageGauge 
                    totalBytes={diskUsage.total}
                    freeBytes={diskUsage.free}
                    usedBytes={diskUsage.used}
                  />
                </div>

                {/* DOWNLOAD QUEUE */}
                <div className="glass-panel" style={{ flex: 1, minHeight: '220px' }}>
                  <div className="panel-header" style={{ marginBottom: '0.75rem' }}>
                    <span className="panel-title">
                      <History size={14} style={{ color: 'var(--primary)' }} />
                      Queue Status
                    </span>
                    <span className="panel-badge" style={{ background: 'rgba(255,255,255,0.04)', color: '#cbd5e1', borderColor: 'rgba(255,255,255,0.06)' }}>
                      {pendingDownloads.length} pending
                    </span>
                  </div>

                  <div className="queue-side-list">
                    {pendingDownloads.length === 0 ? (
                      <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b', fontSize: '0.75rem', fontWeight: 600, padding: '2rem 0' }}>
                        No pending downloads
                      </div>
                    ) : (
                      pendingDownloads.map((job) => (
                        <div 
                          key={job.id} 
                          onClick={() => setSelectedJobId(job.id)}
                          className="queue-side-item"
                        >
                          <div className="queue-side-meta">
                            <div className="queue-side-title">{job.accession}</div>
                            <div className="queue-side-subtitle">{job.methods.join(', ')}</div>
                          </div>
                          <span className="queue-side-badge badge-pending">
                            Pending
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </div>

              </div>

            </div>

            {/* LIVE CONSOLE LOGS (WIDE BOTTOM ROW) */}
            <div className="glass-panel console-panel">
              
              <div className="console-title-row">
                <div className="console-title-group">
                  <span className="console-indicator-dot" />
                  <span className="panel-title" style={{ color: '#f1f5f9' }}>
                    <Terminal size={15} style={{ color: 'var(--cyan)' }} />
                    Live Console Logs {activeJob ? `: ${activeJob.accession} (${activeJob.id})` : ''}
                  </span>
                </div>

                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  {activeJob && (activeJob.status === 'running' || activeJob.status === 'pending') && (
                    <button 
                      onClick={() => handleCancelJob(activeJob.id)}
                      className="btn btn-danger"
                      style={{ padding: '0.35rem 0.75rem', fontSize: '0.75rem' }}
                    >
                      Cancel Job
                    </button>
                  )}
                  <button 
                    onClick={() => {
                      if (activeJob) {
                        setJobs(prev => ({
                          ...prev,
                          [activeJob.id]: {
                            ...prev[activeJob.id],
                            logs: []
                          }
                        }));
                      }
                    }}
                    className="btn btn-secondary"
                    style={{ padding: '0.35rem 0.75rem', fontSize: '0.75rem' }}
                  >
                    Clear Logs
                  </button>
                </div>
              </div>

              {/* Logs terminal box */}
              <div className="console-box">
                {!activeJob ? (
                  <div className="console-empty">
                    Select a job above to monitor live transfer stdout logs
                  </div>
                ) : activeJob.logs.length === 0 ? (
                  <div style={{ color: '#64748b', fontStyle: 'italic', fontSize: '13px' }}>
                    Job initialized. Awaiting engine pipeline logs...
                  </div>
                ) : (
                  <div>
                    {activeJob.logs.map(line => formatLogLine(line))}
                    <div ref={consoleEndRef} />
                  </div>
                )}
              </div>
            </div>

          </div>
        )}

        {/* DOWNLOADS HISTORY TAB */}
        {activeTab === 'downloads' && (
          <div className="glass-panel" style={{ gap: '1.5rem' }}>
            <div className="panel-header" style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '1rem' }}>
              <div>
                <h2 className="subheader-title" style={{ border: 'none', padding: 0 }}>Download History</h2>
                <p className="subheader-desc">Records of completed, failed, and cancelled pipeline tasks</p>
              </div>
              
              <div style={{ fontSize: '0.75rem', fontWeight: 700, display: 'flex', gap: '1rem', color: '#64748b' }}>
                <span style={{ color: 'var(--green)' }}>Completed: {completedDownloads.length}</span>
                <span style={{ color: 'var(--danger)' }}>Failed: {jobList.filter(j => j.status === 'failed').length}</span>
                <span style={{ color: '#fbbf24' }}>Cancelled: {jobList.filter(j => j.status === 'cancelled').length}</span>
              </div>
            </div>

            {/* History Table */}
            <div style={{ overflowX: 'auto' }}>
              <table className="history-table">
                <thead>
                  <tr>
                    <th>Run Accession</th>
                    <th>Submission Date</th>
                    <th>Download Methods</th>
                    <th>Status</th>
                    <th>Logs Preview</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {jobList.length === 0 ? (
                    <tr>
                      <td colSpan="6" style={{ padding: '3rem', textAlign: 'center', color: '#64748b', fontSize: '0.875rem' }}>
                        No download history records found
                      </td>
                    </tr>
                  ) : (
                    jobList.map((job) => {
                      const date = new Date(job.created_at * 1000).toLocaleString();
                      
                      let statusBadge = null;
                      if (job.status === 'completed') {
                        statusBadge = <span className="badge-status completed"><CheckCircle2 size={10} /> Completed</span>;
                      } else if (job.status === 'failed') {
                        statusBadge = <span className="badge-status failed"><XCircle size={10} /> Failed</span>;
                      } else if (job.status === 'cancelled') {
                        statusBadge = <span className="badge-status cancelled"><AlertCircle size={10} /> Cancelled</span>;
                      } else {
                        statusBadge = <span className="badge-status active"><Activity size={10} /> Active</span>;
                      }

                      return (
                        <tr 
                          key={job.id} 
                          onClick={() => {
                            setSelectedJobId(job.id);
                            setActiveTab('dashboard');
                          }}
                        >
                          <td className="table-accession">
                            <span className="table-accession-icon">🎣</span>
                            {job.accession}
                          </td>
                          <td style={{ color: '#64748b' }}>{date}</td>
                          <td style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: '#64748b' }}>{job.methods.join(', ')}</td>
                          <td>{statusBadge}</td>
                          <td style={{ maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#64748b' }}>
                            {job.logs[job.logs.length - 1] || 'No engine logs recorded'}
                          </td>
                          <td className="action-cell" onClick={(e) => e.stopPropagation()}>
                            <button
                              onClick={() => {
                                setJobs(prev => {
                                  const next = { ...prev };
                                  delete next[job.id];
                                  return next;
                                });
                                showToast(`Removed job record ${job.accession}`);
                              }}
                              className="delete-row-btn"
                              title="Delete record"
                            >
                              <Trash2 size={13} />
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* SETTINGS PANEL TAB */}
        {activeTab === 'settings' && (
          <div className="settings-layout">
            
            {/* CONFIGURATION COLUMN */}
            <div className="glass-panel" style={{ padding: '1.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '1rem', marginBottom: '1.25rem' }}>
                <div>
                  <h2 className="subheader-title" style={{ border: 'none', padding: 0 }}>Engine Configurations</h2>
                  <p className="subheader-desc">Customize download protocols, parallel nodes, and directories</p>
                </div>
                <button 
                  onClick={handleDetectAspera}
                  className="btn btn-secondary"
                  style={{ padding: '0.35rem 0.75rem', fontSize: '0.75rem' }}
                >
                  Scan system via ascli
                </button>
              </div>

              <form onSubmit={handleSaveConfig} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                
                <div className="form-row-custom">
                  <div className="form-group-custom">
                    <label className="form-label-custom">Output Storage Directory</label>
                    <div className="input-with-icon-container">
                      <FolderOpen size={16} className="input-icon-overlay" />
                      <input
                        type="text"
                        value={config.output_dir}
                        onChange={(e) => setConfig({ ...config, output_dir: e.target.value })}
                        className="form-input-custom"
                        style={{ paddingLeft: '2.5rem' }}
                        placeholder="e.g. /data/sra_downloads"
                        required
                      />
                    </div>
                  </div>

                  <div className="form-group-custom">
                    <label className="form-label-custom">Parallel Thread Count</label>
                    <input
                      type="number"
                      min="1"
                      max="128"
                      value={config.threads}
                      onChange={(e) => setConfig({ ...config, threads: parseInt(e.target.value) || 4 })}
                      className="form-input-custom"
                      required
                    />
                  </div>
                </div>

                <div className="form-row-custom">
                  <div className="form-group-custom">
                    <label className="form-label-custom">Aspera Executable Path (Ascp)</label>
                    <input
                      type="text"
                      value={config.ascp_bin || ''}
                      onChange={(e) => setConfig({ ...config, ascp_bin: e.target.value })}
                      className="form-input-custom mono"
                      placeholder="Auto-detected if left blank"
                    />
                  </div>

                  <div className="form-group-custom">
                    <label className="form-label-custom">Aspera SSH Bypass Key (.pem)</label>
                    <input
                      type="text"
                      value={config.ascp_key || ''}
                      onChange={(e) => setConfig({ ...config, ascp_key: e.target.value })}
                      className="form-input-custom mono"
                      placeholder="Auto-detected if left blank"
                    />
                  </div>
                </div>

                <div className="form-row-custom" style={{ gridTemplateColumns: '1fr 2fr' }}>
                  <div className="form-group-custom">
                    <label className="form-label-custom">Aspera Port</label>
                    <input
                      type="text"
                      value={config.ascp_port}
                      onChange={(e) => setConfig({ ...config, ascp_port: e.target.value })}
                      className="form-input-custom"
                      required
                    />
                  </div>

                  <div className="form-group-custom">
                    <label className="form-label-custom">Aspera Transport Parameters</label>
                    <input
                      type="text"
                      value={config.ascp_options}
                      onChange={(e) => setConfig({ ...config, ascp_options: e.target.value })}
                      className="form-input-custom mono"
                      required
                    />
                  </div>
                </div>

                <div className="form-row-custom" style={{ borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '1.25rem' }}>
                  <div className="form-group-custom">
                    <label className="form-label-custom">Auto-Retries Count</label>
                    <input
                      type="number"
                      min="0"
                      max="10"
                      value={config.retries}
                      onChange={(e) => setConfig({ ...config, retries: parseInt(e.target.value) || 0 })}
                      className="form-input-custom"
                    />
                  </div>

                  <div className="checkbox-row-custom">
                    <label className="checkbox-label-custom">
                      <input
                        type="checkbox"
                        checked={config.keep_sra}
                        onChange={(e) => setConfig({ ...config, keep_sra: e.target.checked })}
                      />
                      <div>
                        <span className="checkbox-label-title">Keep Decompressed SRA Files</span>
                        <span className="checkbox-label-desc">Retains primary .sra archives post FASTQ conversion</span>
                      </div>
                    </label>
                  </div>
                </div>

                <button type="submit" className="btn btn-primary" style={{ width: '100%', padding: '0.85rem', marginTop: '0.5rem' }}>
                  Save Engine Settings
                </button>
              </form>
            </div>

            {/* STATS INFO CARD */}
            <div className="glass-panel" style={{ padding: '1.5rem', justifyContent: 'space-between' }}>
              <div>
                <span className="panel-title" style={{ marginBottom: '0.75rem' }}>
                  <Cpu size={15} style={{ color: 'var(--primary)' }} />
                  System Overview
                </span>
                <p style={{ fontSize: '0.75rem', color: '#64748b', lineHeight: 1.5, marginBottom: '1.25rem' }}>
                  small_fisher interfaces with ENA SRA databases using parallel-fastq-dump nodes to auto-extract genome sequences.
                </p>

                <div>
                  <div className="sys-info-box">
                    <div className="sys-info-meta">
                      <span className="sys-info-title">Parallel cores allocation</span>
                      <span className="sys-info-val">{config.threads} CPU Threads</span>
                    </div>
                    <Cpu size={24} className="sys-info-icon cyan" />
                  </div>

                  <div className="sys-info-box">
                    <div className="sys-info-meta">
                      <span className="sys-info-title">SRA Fallback Engine</span>
                      <span className="sys-info-val">Active</span>
                    </div>
                    <Database size={24} className="sys-info-icon purple" />
                  </div>
                </div>
              </div>

              <div style={{ borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '1rem', marginTop: '1.5rem' }}>
                <span style={{ fontSize: '9.5px', fontWeight: 800, color: '#64748b', textTransform: 'uppercase', display: 'block', marginBottom: '0.5rem' }}>Current Active Configuration</span>
                <div className="config-code-block">
                  <div>DIR: {config.output_dir || '.'}</div>
                  <div>THREADS: {config.threads}</div>
                  <div>ASPERA KEY: {config.ascp_key ? 'RESOLVED ✓' : 'DEFAULT KEY'}</div>
                  <div>RETRIES: {config.retries}</div>
                </div>
              </div>
            </div>

          </div>
        )}

      </main>

      {/* FOOTER */}
      <footer className="app-footer">
        <span>© 2026 small_fisher open source bio-engine.</span>
        <span className="footer-highlight"><ArrowDownRight size={12} /> High Performance Genome Sequence Downloader</span>
      </footer>

      {/* TOAST / NOTIFICATIONS */}
      {notification && (
        <div className={`toast-notif ${notification.type || 'success'}`}>
          <AlertCircle size={16} />
          <span className="toast-text">{notification.message}</span>
        </div>
      )}

      {/* NEW DOWNLOAD MODAL */}
      {isAddModalOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <button 
              onClick={() => setIsAddModalOpen(false)}
              className="modal-close-btn"
            >
              <X size={16} />
            </button>

            <div className="modal-header-row">
              <span className="modal-header-icon">🎣</span>
              <div>
                <h3 className="modal-header-title">New Download Job</h3>
                <p className="modal-header-desc">Submit NCBI ENA accession run</p>
              </div>
            </div>

            <form onSubmit={handleStartDownload} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div className="form-group-custom" style={{ marginBottom: 0 }}>
                <label className="form-label-custom">Accession Identifier</label>
                <input
                  type="text"
                  value={newAccession}
                  onChange={(e) => setNewAccession(e.target.value)}
                  className="form-input-custom"
                  placeholder="e.g. SRR23641780 or GSE188418"
                  required
                  autoFocus
                />
              </div>

              <div className="form-group-custom" style={{ marginBottom: 0, gap: '0.5rem' }}>
                <label className="form-label-custom">Download Protocols (Priority List)</label>
                
                <div className="modal-protocols-box">
                  <label className="protocol-checkbox-label">
                    <input
                      type="checkbox"
                      checked={newMethods.ascp}
                      onChange={(e) => setNewMethods({ ...newMethods, ascp: e.target.checked })}
                    />
                    <div>
                      <span className="protocol-title">ENA Aspera (ena-ascp)</span>
                      <span className="protocol-desc">High-speed commercial UDP transfer</span>
                    </div>
                  </label>

                  <label className="protocol-checkbox-label">
                    <input
                      type="checkbox"
                      checked={newMethods.prefetch}
                      onChange={(e) => setNewMethods({ ...newMethods, prefetch: e.target.checked })}
                    />
                    <div>
                      <span className="protocol-title">NCBI Prefetch (prefetch)</span>
                      <span className="protocol-desc">NCBI native SRA download + local split</span>
                    </div>
                  </label>

                  <label className="protocol-checkbox-label">
                    <input
                      type="checkbox"
                      checked={newMethods.ftp}
                      onChange={(e) => setNewMethods({ ...newMethods, ftp: e.target.checked })}
                    />
                    <div>
                      <span className="protocol-title">ENA FTP fallback (ena-ftp)</span>
                      <span className="protocol-desc">EBI public FTP download via wget/curl</span>
                    </div>
                  </label>
                </div>
              </div>

              <div className="modal-actions-row">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="btn btn-secondary"
                  style={{ padding: '0.75rem' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  style={{ padding: '0.75rem' }}
                >
                  Launch Pipeline
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}
