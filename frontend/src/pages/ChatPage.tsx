import { useParams } from "react-router-dom";
import ChatView from "../components/chat/ChatView";
import ChatHome from "../components/chat/ChatHome";

export default function ChatPage() {
  const { conversationId } = useParams();

  if (conversationId) {
    return <ChatView conversationId={conversationId} />;
  }

  return <ChatHome />;
}
