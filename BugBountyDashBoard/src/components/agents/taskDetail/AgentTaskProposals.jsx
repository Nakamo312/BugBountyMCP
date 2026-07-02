import React from 'react'
import { Sparkles } from 'lucide-react'
import { EmptyState, ProposalCard, SectionCard } from '../AgentCards'

export function AgentTaskProposals({ actionBusy, onReview, proposals }) {
  return (
    <SectionCard title="Agent proposals" icon={Sparkles}>
      {proposals?.length > 0 ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {proposals.map((proposal) => (
            <ProposalCard
              key={proposal.proposal_id}
              proposal={proposal}
              busy={actionBusy}
              onAccept={(item) => onReview(item, 'accept')}
              onReject={(item) => onReview(item, 'reject')}
              onSuppress={(item) => onReview(item, 'suppress')}
            />
          ))}
        </div>
      ) : (
        <EmptyState title="No proposals" description="" />
      )}
    </SectionCard>
  )
}
