import React from 'react'

export interface FeedItem {
  id: string
}

interface FeedViewerProps {
  feedItems?: FeedItem[]
}

export const FeedViewer: React.FC<FeedViewerProps> = () => {
  return null
}
