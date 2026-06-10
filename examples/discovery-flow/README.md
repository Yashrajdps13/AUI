# TechConf Registration Hub — Discovery Mode Playground

This project demonstrates the complete end-to-end capabilities of **Discovery Mode** in the `react-agent-bridge` framework. It includes a multi-step conference booking form with routes (`/details`, `/options`, `/payment`, `/success`), sensitive inputs (redacting PII data), derived costs, and checkbox collections.

---

## 🛠️ Step 1: Install Dependencies

Open a terminal in the root workspace directory, run:
```bash
npm install
```
Then navigate to this example folder and install dependencies:
```bash
cd examples/discovery-flow
npm install
```

---

## 🌐 Step 2: Start the React Frontend

Start the Vite development server:
```bash
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 🕵️‍♂️ Step 3: Run Passive Observation (Discovery Mode)

Open a second terminal, navigate here, and run the Python playground:
```bash
cd examples/discovery-flow
python agent.py
```
Select option **`1`** (`Run passive discovery server`).

### Let the observation run:
1. Go to your browser at [http://localhost:5173](http://localhost:5173).
2. Fill out the details (Attendee Name, Email). Click **Next Step**.
3. Select options (Ticket category, sessions). Click **Next Step**.
4. Enter Credit Card details. Click **Confirm and Pay**.
5. Observe the "Bridge Activity Log" in the UI to see how PII data is auto-redacted and recorded.
6. Click **Reset Form** and repeat the sequence **3 or more times** (each page reload/reset represents a session).
7. In the Python terminal, press **`Ctrl+C`** to finalize the observation.

This generates a living **`agent-context.md`** file in this directory. Open it to examine:
* **Slot Annotations**: `@sensitive` markers on email and card numbers, collections list types, and derived total cost.
* **Workflows**: Multi-step flow steps extracted from sequential observation.
* **Constraints**: sequencing, write-protection, and page routing scope rules.

---

## 🤖 Step 4: Try Golden Trace Replay

Once `agent-context.md` is generated, run `agent.py` again:
```bash
python agent.py
```
Select option **`2`** (`Run automated agent runner`).

1. Open your browser, reset the form if needed.
2. The agent will execute the goal compiled from your query:
   * **Run 1 (Direct LLM)**: Plans step by step using LLM calls. This compiles and records a **Golden Trace** in the local database.
   * **Prompt**: Once Run 1 completes, click **Reset Form** in the browser, and press **Enter** in the Python console.
   * **Run 2 (Golden Trace Replay)**: The runner detects a matching golden trace and executes it instantly with **0 LLM calls**, resulting in an immediate 50–80% planning speedup!
