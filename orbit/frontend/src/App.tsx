import { useState } from "react";
import type React from "react";
import LeftPanel from "./components/LeftPanel";
import Chart from "./components/Chart";
import VerdictStrip from "./components/VerdictStrip";
import ScorecardStrip from "./components/ScorecardStrip";
import RightPanelTop from "./components/RightPanelTop";
import RightPanelBottom from "./components/RightPanelBottom";
import BottomBar from "./components/BottomBar";
import StatusBar from "./components/StatusBar";
import ExecuteModal from "./components/ExecuteModal";

export default function App(): React.ReactElement {
  const [executeModalOpen, setExecuteModalOpen] = useState(false);

  return (
    <div id="orbit-root">
      <div className="left-panel">
        <LeftPanel />
      </div>

      <div className="center-panel">
        <div className="center-panel__verdict">
          <VerdictStrip
            onExecute={() => {
              setExecuteModalOpen(true);
            }}
          />
        </div>
        <div className="center-panel__chart">
          <Chart />
        </div>
        <div className="center-panel__scorecard">
          <ScorecardStrip />
        </div>
      </div>

      <div className="right-panel">
        <div className="right-panel__top">
          <RightPanelTop />
        </div>
        <div className="right-panel__bottom">
          <RightPanelBottom />
        </div>
      </div>

      <div className="bottom-bar">
        <BottomBar />
      </div>

      <div className="status-bar">
        <StatusBar />
      </div>

      {executeModalOpen && (
        <ExecuteModal
          onClose={() => {
            setExecuteModalOpen(false);
          }}
        />
      )}
    </div>
  );
}
