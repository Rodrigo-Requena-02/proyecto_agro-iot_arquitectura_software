import Dashboard from "./Dashboard.jsx";
import Login from "./Login.jsx";
import { useAuthViewModel } from "./viewmodels.js";

export default function App() {
  const auth = useAuthViewModel();
  return auth.user ? <Dashboard user={auth.user} onLogout={auth.logout} /> : <Login auth={auth} />;
}
