import { AgentWorkspaceView } from '../components/agents/AgentWorkspacePanels'
import { useAgentWorkspace } from '../hooks/useAgentWorkspace'

export default function AgentWorkspace() {
  const state = useAgentWorkspace()
  return <AgentWorkspaceView state={state} />
}
