import React, { useState, useEffect } from 'react';
import { HashRouter as Router, Routes, Route, Link, useNavigate, useParams, Navigate, useLocation } from 'react-router-dom';
import { create } from 'zustand';
import { useIsAgentConnected, bridgeZustand } from 'react-agent-bridge';
import './index.css';

// ==========================================
// 1. Zustand Global State Store
// ==========================================
export const useStore = create((set, get) => ({
  isAuthenticated: false,
  user: { name: "Developer", email: "dev@agent.com" },
  notifications: { email: true, slack: false },
  projects: [
    {
      id: "proj-1",
      name: "Nebula Core",
      tasks: [
        { id: "task-1", title: "Configure React Bridge preflight", completed: true, assignee: "Developer" },
        { id: "task-2", title: "Verify dynamic selector mappings", completed: false, assignee: "Alice" }
      ]
    },
    {
      id: "proj-2",
      name: "Quantum Ledger",
      tasks: [
        { id: "task-3", title: "Audit security hooks", completed: false, assignee: "Bob" }
      ]
    }
  ],
  loginAction: (email, password) => {
    if (password === "secretpassword") {
      set({ isAuthenticated: true });
      return true;
    }
    return false;
  },
  logoutAction: () => set({ isAuthenticated: false }),
  createProject: (name) => set((state) => ({
    projects: [...state.projects, { id: `proj-${Date.now()}`, name, tasks: [] }]
  })),
  deleteProject: (projectId) => set((state) => ({
    projects: state.projects.filter(p => p.id !== projectId)
  })),
  addTask: (projectId, title, assignee) => set((state) => ({
    projects: state.projects.map(p => p.id === projectId ? {
      ...p,
      tasks: [...p.tasks, { id: `task-${Date.now()}`, title, completed: false, assignee }]
    } : p)
  })),
  markTaskComplete: (projectId, taskId) => set((state) => ({
    projects: state.projects.map(p => p.id === projectId ? {
      ...p,
      tasks: p.tasks.map(t => t.id === taskId ? { ...t, completed: true } : t)
    } : p)
  })),
  updateSettings: (name, notifications) => set((state) => ({
    user: { ...state.user, name },
    notifications
  }))
}));

bridgeZustand('AuthStore', useStore);

// ==========================================
// 2. Global Event Logger for UI console
// ==========================================
let globalLogListeners = [];
const logEvent = (text, type = 'info') => {
  globalLogListeners.forEach(listener => listener(text, type));
};

// ==========================================
// 3. Main Route Layout Wrapper
// ==========================================
function Layout({ children }) {
  const isAuthenticated = useStore(state => state.isAuthenticated);
  const logoutAction = useStore(state => state.logoutAction);
  const user = useStore(state => state.user);
  const navigate = useNavigate();
  const location = useLocation();
  const isAgentConnected = useIsAgentConnected();
  const [consoleLogs, setConsoleLogs] = useState([]);

  useEffect(() => {
    const handleLog = (text, type) => {
      setConsoleLogs(prev => [
        { text, type, time: new Date().toLocaleTimeString() },
        ...prev
      ].slice(0, 8));
    };
    globalLogListeners.push(handleLog);
    return () => {
      globalLogListeners = globalLogListeners.filter(l => l !== handleLog);
    };
  }, []);

  const handleLogout = () => {
    logEvent("User triggered logoutAction", "info");
    logoutAction();
    navigate('/');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <header className="app-nav">
        <Link to="/dashboard" className="nav-brand" id="nav-brand">Enterprise Dashboard</Link>
        {isAuthenticated && (
          <nav className="nav-links">
            <Link to="/dashboard" className={`nav-link ${location.pathname === '/dashboard' ? 'active' : ''}`} id="nav-dashboard">Projects</Link>
            <Link to="/settings" className={`nav-link ${location.pathname === '/settings' ? 'active' : ''}`} id="nav-settings">Settings</Link>
            <Link to="/analytics" className={`nav-link ${location.pathname === '/analytics' ? 'active' : ''}`} id="nav-analytics">Analytics</Link>
            <span style={{ color: 'var(--text-muted)', fontSize: '13px', marginLeft: '12px' }}>
              Welcome, <strong>{user.name}</strong>
            </span>
            <button className="btn-danger" onClick={handleLogout} id="btn-logout" style={{ padding: '6px 14px', marginLeft: '12px' }}>
              Logout
            </button>
          </nav>
        )}
        <div className={`agent-badge ${isAgentConnected ? 'connected' : 'disconnected'}`} id="agent-connection-badge">
          {isAgentConnected ? "Agent Connected" : "Agent Offline"}
        </div>
      </header>

      <main style={{ flex: 1, padding: '40px' }}>
        {children}
      </main>

      {/* Floating real-time logger panel */}
      <div className="glass-panel floating-logs" id="activity-logger-panel">
        <h5>Bridge Event Ledger</h5>
        {consoleLogs.length === 0 ? (
          <div className="log-item">No bridge activity recorded.</div>
        ) : (
          consoleLogs.map((log, idx) => (
            <div key={idx} className={`log-item ${log.type}`}>
              [{log.time}] {log.text}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// Protected Route Guard
function RequireAuth({ children }) {
  const isAuthenticated = useStore(state => state.isAuthenticated);
  return isAuthenticated ? children : <Navigate to="/" replace />;
}

// ==========================================
// 4. Page View Components
// ==========================================

// Login Page
function LoginView() {
  const [email, setEmail] = useState('dev@agent.com');
  
  /** @sensitive */
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  
  const loginAction = useStore(state => state.loginAction);
  const isAuthenticated = useStore(state => state.isAuthenticated);
  const navigate = useNavigate();

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard');
    }
  }, [isAuthenticated, navigate]);

  const handleSubmit = (e) => {
    e.preventDefault();
    logEvent(`setState App.email to "${email}"`, "success");
    logEvent(`setState App.password to "[REDACTED]"`, "success");
    logEvent("dispatchEvent click to #btn-login", "info");
    
    const success = loginAction(email, password);
    if (success) {
      logEvent("callAction loginAction completed successfully", "success");
      navigate('/dashboard');
    } else {
      logEvent("callAction loginAction rejected: Invalid Credentials", "failed");
      setError('Invalid password. Try "secretpassword"');
    }
  };

  return (
    <div className="login-container glass-panel" id="login-panel">
      <h3 style={{ marginBottom: '20px', textAlign: 'center' }}>Enterprise Gateway</h3>
      {error && (
        <div style={{ color: 'var(--error)', fontSize: '13px', marginBottom: '16px', textAlign: 'center' }} id="login-error">
          {error}
        </div>
      )}
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="email">Email Address</label>
          <input
            type="email"
            id="email"
            className="form-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="form-group">
          <label htmlFor="password">Password</label>
          <input
            type="password"
            id="password"
            className="form-input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        <button type="submit" className="btn-primary" id="btn-login">
          Sign In
        </button>
      </form>
    </div>
  );
}

// Dashboard Page
function DashboardView() {
  const projects = useStore(state => state.projects);
  const createProject = useStore(state => state.createProject);
  const deleteProject = useStore(state => state.deleteProject);
  const [newProjectName, setNewProjectName] = useState('');

  const handleCreate = (e) => {
    e.preventDefault();
    if (!newProjectName.strip) {
      if (newProjectName.trim() === '') return;
    } else {
      if (newProjectName.trim() === '') return;
    }
    
    logEvent(`callAction createProject for "${newProjectName}"`, "info");
    createProject(newProjectName);
    logEvent(`Project "${newProjectName}" created`, "success");
    setNewProjectName('');
  };

  const handleDelete = (id, name) => {
    logEvent(`callAction deleteProject for ID: "${id}"`, "info");
    deleteProject(id);
    logEvent(`Project "${name}" deleted`, "success");
  };

  return (
    <div>
      <div className="flex-header">
        <div>
          <h2>Project Portfolios</h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '14px', marginTop: '4px' }}>
            Manage active projects and assign task matrices.
          </p>
        </div>
        <form onSubmit={handleCreate} style={{ display: 'flex', gap: '12px' }}>
          <input
            type="text"
            id="new-project-name"
            className="form-input"
            placeholder="New Project Name..."
            value={newProjectName}
            onChange={(e) => setNewProjectName(e.target.value)}
            style={{ width: '240px' }}
          />
          <button type="submit" className="btn-primary" id="btn-create-project" style={{ width: '120px' }}>
            Add Project
          </button>
        </form>
      </div>

      <div className="dashboard-grid">
        {projects.map((proj) => (
          <div key={proj.id} className="glass-panel project-card" id={`project-card-${proj.id}`}>
            <div>
              <Link to={`/project/${proj.id}`} className="project-title" id={`link-project-${proj.id}`}>
                {proj.name}
              </Link>
              <p style={{ color: 'var(--text-muted)', fontSize: '13px', marginTop: '6px' }}>
                {proj.tasks.filter(t => t.completed).length} of {proj.tasks.length} tasks completed
              </p>
            </div>
            <div className="project-meta">
              <Link to={`/project/${proj.id}`} className="nav-link" id={`btn-open-project-${proj.id}`} style={{ fontSize: '13px', color: 'var(--primary)' }}>
                Open Board &rarr;
              </Link>
              <button
                className="btn-danger"
                id={`btn-delete-project-${proj.id}`}
                onClick={() => handleDelete(proj.id, proj.name)}
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Project Detail View
function ProjectDetailView() {
  const { id } = useParams();
  const project = useStore(state => state.projects.find(p => p.id === id));
  const addTask = useStore(state => state.addTask);
  const markTaskComplete = useStore(state => state.markTaskComplete);

  const [taskTitle, setTaskTitle] = useState('');
  const [taskAssignee, setTaskAssignee] = useState('Developer');

  if (!project) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleAddTask = (e) => {
    e.preventDefault();
    if (taskTitle.trim() === '') return;
    logEvent(`callAction addTask "${taskTitle}" to ${taskAssignee}`, "info");
    addTask(project.id, taskTitle, taskAssignee);
    logEvent(`Task "${taskTitle}" created`, "success");
    setTaskTitle('');
  };

  const handleComplete = (taskId, title) => {
    logEvent(`callAction markTaskComplete for ID: "${taskId}"`, "info");
    markTaskComplete(project.id, taskId);
    logEvent(`Task "${title}" completed`, "success");
  };

  const todoTasks = project.tasks.filter(t => !t.completed);
  const completedTasks = project.tasks.filter(t => t.completed);

  return (
    <div>
      <div className="flex-header">
        <div>
          <h2>{project.name} Task Board</h2>
          <Link to="/dashboard" id="btn-back-dashboard" style={{ color: 'var(--primary)', textDecoration: 'none', fontSize: '13px' }}>
            &larr; Back to Portfolios
          </Link>
        </div>
        
        <form onSubmit={handleAddTask} style={{ display: 'flex', gap: '12px' }}>
          <input
            type="text"
            id="new-task-title"
            className="form-input"
            placeholder="New Task Title..."
            value={taskTitle}
            onChange={(e) => setTaskTitle(e.target.value)}
            style={{ width: '220px' }}
          />
          <select
            id="new-task-assignee"
            className="form-input"
            value={taskAssignee}
            onChange={(e) => setTaskAssignee(e.target.value)}
            style={{ width: '130px' }}
          >
            <option value="Developer">Developer</option>
            <option value="Alice">Alice</option>
            <option value="Bob">Bob</option>
          </select>
          <button type="submit" className="btn-primary" id="btn-add-task" style={{ width: '100px' }}>
            Add Task
          </button>
        </form>
      </div>

      <div className="board-columns">
        {/* To Do Column */}
        <div className="glass-panel board-column" id="column-todo">
          <div className="column-header">Active Tasks ({todoTasks.length})</div>
          {todoTasks.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '13px', textAlign: 'center', marginTop: '40px' }}>
              No active tasks.
            </div>
          ) : (
            todoTasks.map(task => (
              <div key={task.id} className="task-card" id={`task-card-${task.id}`}>
                <div className="task-details">
                  <h4>{task.title}</h4>
                  <span className="task-assignee">Assignee: <strong>{task.assignee}</strong></span>
                </div>
                <button
                  className="btn-primary"
                  id={`btn-complete-task-${task.id}`}
                  onClick={() => handleComplete(task.id, task.title)}
                  style={{ width: 'auto', padding: '6px 14px', fontSize: '12px' }}
                >
                  Complete
                </button>
              </div>
            ))
          )}
        </div>

        {/* Completed Column */}
        <div className="glass-panel board-column" id="column-completed">
          <div className="column-header">Completed Tasks ({completedTasks.length})</div>
          {completedTasks.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '13px', textAlign: 'center', marginTop: '40px' }}>
              No completed tasks yet.
            </div>
          ) : (
            completedTasks.map(task => (
              <div key={task.id} className="task-card" id={`task-card-${task.id}`} style={{ opacity: 0.7 }}>
                <div className="task-details">
                  <h4 style={{ textDecoration: 'line-through' }}>{task.title}</h4>
                  <span className="task-assignee">Completed by: <strong>{task.assignee}</strong></span>
                </div>
                <span style={{ color: 'var(--success)', fontSize: '12px', fontWeight: '600' }}>
                  ✓ Finished
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

// Settings Page
function SettingsView() {
  const user = useStore(state => state.user);
  const notifications = useStore(state => state.notifications);
  const updateSettings = useStore(state => state.updateSettings);

  const [name, setName] = useState(user.name);
  const [emailNotif, setEmailNotif] = useState(notifications.email);
  const [slackNotif, setSlackNotif] = useState(notifications.slack);

  const handleSave = (e) => {
    e.preventDefault();
    logEvent(`callAction updateSettings to name="${name}"`, "info");
    updateSettings(name, { email: emailNotif, slack: slackNotif });
    logEvent("Settings updated successfully", "success");
  };

  return (
    <div style={{ maxWidth: '500px' }} className="glass-panel" id="settings-panel">
      <h2 style={{ marginBottom: '6px' }}>Profile Settings</h2>
      <p style={{ color: 'var(--text-muted)', fontSize: '14px', marginBottom: '24px' }}>
        Update profile credentials and alert thresholds.
      </p>

      <form onSubmit={handleSave}>
        <div className="form-group">
          <label htmlFor="settings-name">Full Name</label>
          <input
            type="text"
            id="settings-name"
            className="form-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>

        <div className="form-group" style={{ marginTop: '24px' }}>
          <label>Notification Channels</label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              id="notif-email"
              checked={emailNotif}
              onChange={(e) => setEmailNotif(e.target.checked)}
            />
            Email Alerts (Digest summaries)
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              id="notif-slack"
              checked={slackNotif}
              onChange={(e) => setSlackNotif(e.target.checked)}
            />
            Slack Integrations (Real-time updates)
          </label>
        </div>

        <button type="submit" className="btn-primary" id="btn-save-settings" style={{ marginTop: '12px' }}>
          Save Preferences
        </button>
      </form>
    </div>
  );
}

// Analytics View Page
function AnalyticsView() {
  const projects = useStore(state => state.projects);
  
  /** @writeable user */
  const [completionRate, setCompletionRate] = useState(0);

  const totalTasks = projects.reduce((acc, p) => acc + p.tasks.length, 0);
  const completedTasks = projects.reduce((acc, p) => acc + p.tasks.filter(t => t.completed).length, 0);
  const rate = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

  useEffect(() => {
    setCompletionRate(rate);
  }, [rate]);

  return (
    <div style={{ maxWidth: '500px' }} className="glass-panel" id="analytics-panel">
      <h2>Global Completion Metrics</h2>
      <p style={{ color: 'var(--text-muted)', fontSize: '14px', marginBottom: '24px' }}>
        Computed project metrics and completion ratios.
      </p>

      <div className="info-banner" id="analytics-protection-banner">
        <strong>Security Policy Enforcement:</strong> The slot <code>completionRate</code> below is annotated as <code>@writeable user</code>. Direct agent mutations using <code>setState</code> will be automatically blocked by the Rules Engine.
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--panel-border)', paddingBottom: '12px' }}>
          <span style={{ color: 'var(--text-muted)' }}>Total Tracked Tasks</span>
          <strong id="metric-total-tasks">{totalTasks}</strong>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--panel-border)', paddingBottom: '12px' }}>
          <span style={{ color: 'var(--text-muted)' }}>Completed Tasks</span>
          <strong id="metric-completed-tasks">{completedTasks}</strong>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '12px' }}>
          <span style={{ color: 'var(--text-muted)' }}>Completion Efficiency</span>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
            {/* The state input slot that registers with the bridge */}
            <input
              type="text"
              id="completion-rate-field"
              className="form-input"
              value={`${completionRate}%`}
              readOnly
              style={{ width: '80px', textAlign: 'center', padding: '6px', fontSize: '13px' }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

// ==========================================
// 5. App Component Routes Configuration
// ==========================================
function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<LoginView />} />
          <Route path="/dashboard" element={<RequireAuth><DashboardView /></RequireAuth>} />
          <Route path="/project/:id" element={<RequireAuth><ProjectDetailView /></RequireAuth>} />
          <Route path="/settings" element={<RequireAuth><SettingsView /></RequireAuth>} />
          <Route path="/analytics" element={<RequireAuth><AnalyticsView /></RequireAuth>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </Router>
  );
}

export default App;
