import sys
import os
import time
import random
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
import gym
from collections import deque
from datetime import date, timedelta
from google.colab import drive

# 1. MOUNT DRIVE
if not os.path.exists('/content/drive'):
    drive.mount('/content/drive')

# 2. INSTALL YFINANCE
try:
    import yfinance as yf
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    import yfinance as yf

# --- HIGH CONTRAST COLORS ---
class C:
    GREEN = '\033[92m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

# --- CONFIGURATION ---
BRAIN_FILE = "/content/drive/My Drive/world_indices_lstm_v2.pth"
STOCK_LIST = ['^DJI', '^GSPC', '^IXIC', '^HSI', '^FTSE', '^GDAXI']

START_DATE = '2015-01-01'
yesterday = date.today() - timedelta(days=1)
END_DATE = yesterday.strftime('%Y-%m-%d')

SEQUENCE_LENGTH = 30   
BATCH_SIZE = 32       
GAMMA = 0.95           
LEARNING_RATE = 0.0001 
MEMORY_SIZE = 10000

# ==========================================
# 1. THE "RELATIVE VISION" ENVIRONMENT
# ==========================================
class YahooFinanceEnv(gym.Env):
    def __init__(self, stock_list, start, end, seq_len):
        self.stock_data = {}
        self.tickers = stock_list
        self.seq_len = seq_len
        
        print(f"{C.CYAN}{C.BOLD}Downloading World Indices (Stationary Mode)...{C.RESET}")
        for ticker in stock_list:
            try:
                df = yf.download(ticker, start=start, end=end, progress=False)
                if len(df) > 500: 
                    self.stock_data[ticker] = self._process_data(df)
                    print(f"{C.GREEN}✅ Loaded {ticker}{C.RESET}")
            except Exception as e:
                print(f"{C.RED}❌ Error {ticker}: {e}{C.RESET}")
        
        if not self.stock_data: raise ValueError("No data loaded!")
        
        self.action_space = gym.spaces.Discrete(3)
        self.observation_space = gym.spaces.Box(low=-np.inf, high=np.inf, shape=(seq_len, 10), dtype=np.float32)
        self.reset()

    def _process_data(self, df):
        close = df['Close']
        if isinstance(close, pd.DataFrame): close = close.iloc[:, 0]
        
        df['Returns'] = close.pct_change().fillna(0)
        
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
        
        vol = df['Volume']
        if isinstance(vol, pd.DataFrame): vol = vol.iloc[:, 0]
        vol = vol.replace(0, 1)
        df['RVOL'] = vol / vol.rolling(window=20).mean()

        sma_50 = close.rolling(window=50).mean()
        df['Trend_Score'] = (close - sma_50) / sma_50 

        df = df.dropna()
        return {'prices': close.values[50:], 'data': df}

    def reset(self):
        self.current_ticker = random.choice(list(self.stock_data.keys()))
        dataset = self.stock_data[self.current_ticker]
        self.prices = dataset['prices']
        self.df_clean = dataset['data']
        self.current_step = self.seq_len 
        self.position = 0
        self.entry_price = 0
        self.entry_step = 0
        self.cash = 10000
        self.shares = 0
        self.portfolio_value = 10000
        return self._next_observation()

    def _next_observation(self):
        obs_window = self.df_clean.iloc[self.current_step - self.seq_len : self.current_step]
        sequence = []
        for i in range(self.seq_len):
            row = obs_window.iloc[i]
            def get_val(col): return row[col].iloc[0] if isinstance(row[col], pd.Series) else row[col]

            features = [
                get_val('Returns') * 100,      
                get_val('RSI') / 100.0,        
                get_val('MACD'),               
                get_val('Signal_Line'),        
                get_val('Trend_Score') * 10,   
                get_val('RVOL'),               
                0.0, 0.0, 0.0,                 
                float(self.position)           
            ]
            sequence.append(features)
        return np.array(sequence, dtype=np.float32)

    def step(self, action):
        self.current_step += 1
        current_price = self.prices[self.current_step]
        prev_val = self.portfolio_value
        
        forced_sell = False
        if self.position == 1:
            current_loss_pct = (current_price - self.entry_price) / self.entry_price
            if current_loss_pct < -0.03: 
                action = 2 
                forced_sell = True

        if action == 1 and self.position == 0: 
            self.position = 1
            self.shares = self.cash / current_price
            self.cash = 0
            self.entry_price = current_price
            self.entry_step = self.current_step
            
        elif action == 2 and self.position == 1: 
            self.position = 0
            self.cash = self.shares * current_price
            self.shares = 0

        if self.position == 1:
            self.portfolio_value = self.shares * current_price
        else:
            self.portfolio_value = self.cash

        profit_pct = (self.portfolio_value - prev_val) / prev_val * 100
        
        if forced_sell:
            reward = -10.0 
        elif profit_pct > 0:
            reward = profit_pct * 10.0 
        elif profit_pct < 0:
            reward = profit_pct * 2.0  
        else:
            reward = -0.1 

        done = False
        if self.current_step >= len(self.prices) - 2:
            done = True
            
        return self._next_observation(), reward, done, {}

# ==========================================
# 2. LSTM BRAIN
# ==========================================
class LSTM_DQN(nn.Module):
    def __init__(self, input_dim, hidden_dim, action_dim):
        super(LSTM_DQN, self).__init__()
        self.lstm = nn.LSTM(input_size=input_dim, hidden_size=hidden_dim, batch_first=True)
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Linear(64, action_dim)
        )
    def forward(self, x):
        lstm_out, (hn, cn) = self.lstm(x)
        return self.fc(hn[-1])

# ==========================================
# 3. AGENT
# ==========================================
class Agent:
    def __init__(self, state_dim, action_dim, save_path):
        self.action_dim = action_dim
        self.epsilon = 1.0
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.995
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.save_path = save_path
        
        self.policy_net = LSTM_DQN(10, 128, action_dim).to(self.device)
        self.target_net = LSTM_DQN(10, 128, action_dim).to(self.device)
        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=LEARNING_RATE)
        self.memory = deque(maxlen=MEMORY_SIZE)
        self.loss_fn = nn.MSELoss()

    def act(self, state):
        if random.random() < self.epsilon:
            today = state[-1] 
            rsi = today[1] * 100
            macd = today[2]
            signal = today[3]
            trend = today[4]
            position = today[9]
            
            if position == 0:
                if trend > 0 and rsi < 65 and macd > signal: return 1 
            elif position == 1:
                if macd < signal: return 2 
            
            return random.randint(0, self.action_dim - 1)

        state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        with torch.no_grad():
            return torch.argmax(self.policy_net(state_t)).item()

    def remember(self, state, action, reward, next_state, done):
        self.memory.append((state, action, reward, next_state, done))

    def replay(self):
        if len(self.memory) < BATCH_SIZE: return
        batch = random.sample(self.memory, BATCH_SIZE)
        state, action, reward, next_state, done = zip(*batch)
        state = torch.FloatTensor(np.array(state)).to(self.device)
        action = torch.LongTensor(action).unsqueeze(1).to(self.device)
        reward = torch.FloatTensor(reward).unsqueeze(1).to(self.device)
        next_state = torch.FloatTensor(np.array(next_state)).to(self.device)
        done = torch.FloatTensor(done).unsqueeze(1).to(self.device)
        current_q = self.policy_net(state).gather(1, action)
        next_q = self.target_net(next_state).max(1)[0].unsqueeze(1)
        expected_q = reward + (GAMMA * next_q * (1 - done))
        loss = self.loss_fn(current_q, expected_q)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        if self.epsilon > self.epsilon_min: self.epsilon *= self.epsilon_decay

    def save(self):
        torch.save(self.policy_net.state_dict(), self.save_path)

# ==========================================
# 4. TRAINING (HIGH VISIBILITY MODE)
# ==========================================
print("\n" + "="*50)
print(f"{C.YELLOW}{C.BOLD} STARTING 'RELATIVE VISION' LSTM V2{C.RESET}")
print(f"{C.CYAN} Features: Stop Loss (-3%), 30-Day Memory, Normalized Inputs{C.RESET}")
print("="*50)

env = YahooFinanceEnv(STOCK_LIST, START_DATE, END_DATE, SEQUENCE_LENGTH)
agent = Agent(10, 3, BRAIN_FILE)

try:
    episode = 0
    while True:
        episode += 1
        state = env.reset()
        total_reward = 0
        done = False
        
        while not done:
            action = agent.act(state)
            next_state, reward, done, _ = env.step(action)
            agent.remember(state, action, reward, next_state, done)
            agent.replay()
            state = next_state
            total_reward += reward
        
        # --- COLOR CODED LOGGING ---
        ticker_txt = f"{C.CYAN}{env.current_ticker}{C.RESET}"
        
        if total_reward > 0:
            profit_txt = f"{C.GREEN}{total_reward:.2f}%{C.RESET}"
        else:
            profit_txt = f"{C.RED}{total_reward:.2f}%{C.RESET}"
            
        if episode % 5 == 0:
            agent.target_net.load_state_dict(agent.policy_net.state_dict())
            agent.save()
            print(f"Ep {episode} | {ticker_txt} | Profit: {profit_txt} | Epsilon: {agent.epsilon:.2f} | {C.GREEN}✅ Saved{C.RESET}")
        else:
            print(f"Ep {episode} | {ticker_txt} | Profit: {profit_txt}")

except KeyboardInterrupt:
    print(f"{C.YELLOW}Training Stopped. Saving...{C.RESET}")
    agent.save()
