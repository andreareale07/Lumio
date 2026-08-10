const appName = import.meta.env.VITE_APP_NAME || "Lumio";
const appTagline = import.meta.env.VITE_APP_TAGLINE || "See your money clearly.";

function App() {
  return (
    <main>
      <h1>{appName}</h1>
      <p>{appTagline}</p>
    </main>
  );
}

export default App;
