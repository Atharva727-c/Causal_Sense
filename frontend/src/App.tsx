import Sidebar from './components/Sidebar'
import ChatArea from './components/ChatArea'
import DataPanel from './components/DataPanel'
import { useChat } from './hooks/useChat'
import { useFiles } from './hooks/useFiles'

export default function App() {
  const { files, uploadFile, removeFile, isUploading, totalUsed, totalCapacity } = useFiles()
  const { chats, activeChat, activeChatId, setActiveChatId, sendMessage, runFeature, sendEdaFollowup, newChat, renameChat, deleteChat, isLoading } = useChat(files)

  return (
    <div style={{ display: 'flex', width: '100%', height: '100vh', overflow: 'hidden' }}>
      <Sidebar
        chats={chats}
        activeChatId={activeChatId}
        onSelectChat={setActiveChatId}
        onNewChat={newChat}
        onRenameChat={renameChat}
        onDeleteChat={deleteChat}
      />
      <ChatArea
        chat={activeChat}
        chatTitle={activeChat.title}
        isLoading={isLoading}
        onSend={sendMessage}
        onUpload={uploadFile}
        onFeature={runFeature}
        onFollowup={sendEdaFollowup}
      />
      <DataPanel
        files={files}
        onUpload={uploadFile}
        onRemove={removeFile}
        isUploading={isUploading}
        totalUsed={totalUsed}
        totalCapacity={totalCapacity}
      />
    </div>
  )
}
