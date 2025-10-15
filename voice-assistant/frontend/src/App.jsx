import React, { useState, useEffect, useRef } from 'react';
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useTracks,
  useRoomContext,
  useLocalParticipant,
} from '@livekit/components-react';
import '@livekit/components-styles';
import { Track } from 'livekit-client';

const serverUrl = process.env.REACT_APP_LIVEKIT_URL || 'ws://localhost:7880';
const backendUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';

function App() {
  const [token, setToken] = useState('');
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    fetch(`${backendUrl}/token`)
      .then((res) => res.json())
      .then((data) => {
        console.log('✅ 获取到 token:', data.token);
        setToken(data.token);
      })
      .catch((err) => console.error('❌ 获取token失败:', err));
  }, []);

  return (
    <div style={{ padding: '20px' }}>
      <h1>🎙️ Voice Assistant</h1>
      <p style={{ fontSize: '12px', color: '#666' }}>
        LiveKit URL: {serverUrl}
      </p>
      
      {token ? (
        <LiveKitRoom
          token={token}
          serverUrl={serverUrl}
          connect={true}
          audio={true}
          video={false}
          onConnected={() => {
            console.log('✅ 已连接到房间');
            setIsConnected(true);
          }}
          onDisconnected={() => {
            console.log('❌ 已断开连接');
            setIsConnected(false);
          }}
          onError={(error) => {
            console.error('❌ LiveKit 连接错误:', error);
          }}
        >
          <div>
            {isConnected ? (
              <p style={{ color: 'green', fontWeight: 'bold' }}>
                ✓ 已连接到 LiveKit - 请开始说话
              </p>
            ) : (
              <p style={{ color: 'orange' }}>⏳ 连接中...</p>
            )}
          </div>

          <RoomAudioRenderer />
          <MicrophoneManager />
          <RoomStatus />
          <AudioManager />
        </LiveKitRoom>
      ) : (
        <p>⏳ 正在获取token...</p>
      )}
    </div>
  );
}

// ✅ 修复：添加 setMicEnabled 和 setError
function MicrophoneManager() {
  const { localParticipant } = useLocalParticipant();
  const [micEnabled, setMicEnabled] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!localParticipant) return;

    const publishMicrophone = async () => {
      try {
        console.log('🎤 请求麦克风权限...');
        
        const devices = await navigator.mediaDevices.enumerateDevices();
        const audioDevices = devices.filter(d => d.kind === 'audioinput');
        console.log('🎧 可用音频设备:', audioDevices);

        await localParticipant.setMicrophoneEnabled(true);
        console.log('✅ 麦克风已启用');
        
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        const micTrack = localParticipant.getTrackPublication(Track.Source.Microphone);
        console.log('📡 麦克风轨道:', {
          sid: micTrack?.trackSid,
          isMuted: micTrack?.isMuted,
          isEnabled: micTrack?.isEnabled,
          track: micTrack?.track
        });

        if (micTrack?.track) {
          console.log('✅ 麦克风轨道已成功发布!');
          setMicEnabled(true);  // ✅ 使用正确的 state
        } else {
          console.error('❌ 麦克风轨道未发布');
          setError('麦克风轨道未发布');
        }
      } catch (err) {
        console.error('❌ 发布麦克风失败:', err);
        setError(err.message);
      }
    };

    publishMicrophone();
  }, [localParticipant]);

  return (
    <div style={{ 
      margin: '10px 0', 
      padding: '10px', 
      backgroundColor: micEnabled ? '#e8f5e9' : '#fff3e0', 
      borderRadius: '5px' 
    }}>
      <p>
        🎤 麦克风状态: {
          micEnabled 
            ? <span style={{ color: 'green', fontWeight: 'bold' }}>✓ 已启用</span>
            : <span style={{ color: 'orange' }}>⏳ 正在启用...</span>
        }
      </p>
      {error && (
        <p style={{ color: 'red', fontSize: '12px' }}>
          ⚠️ 错误: {error}
        </p>
      )}
    </div>
  );
}

function RoomStatus() {
  const room = useRoomContext();
  const [participantCount, setParticipantCount] = useState(0);

  useEffect(() => {
    if (!room) return;

    const updateCount = () => {
      const count = room.remoteParticipants.size;
      setParticipantCount(count);
      console.log('👥 远程参与者数量:', count);
      console.log('🎤 本地麦克风状态:', room.localParticipant.isMicrophoneEnabled);
      
      room.remoteParticipants.forEach((participant) => {
        console.log('👤 远程参与者:', participant.identity);
      });
    };

    updateCount();
    room.on('participantConnected', (participant) => {
      console.log('✅ 新参与者加入:', participant.identity);
      updateCount();
    });
    room.on('participantDisconnected', (participant) => {
      console.log('❌ 参与者离开:', participant.identity);
      updateCount();
    });

    return () => {
      room.off('participantConnected', updateCount);
      room.off('participantDisconnected', updateCount);
    };
  }, [room]);

  return (
    <div style={{ 
      margin: '10px0', 
      padding: '10px', 
      backgroundColor: '#f5f5f5', 
      borderRadius: '5px' 
    }}>
      <p>👤 本地用户: {room?.localParticipant.identity || '未知'}</p>
      <p>👥 远程参与者: {participantCount}</p>
      <p>🎤 麦克风: {
        room?.localParticipant.isMicrophoneEnabled 
          ? <span style={{ color: 'green' }}>已启用 ✓</span>
          : <span style={{ color: 'red' }}>已禁用 ✗</span>
      }</p>
    </div>
  );
}

function AudioManager() {
  const tracks = useTracks([
    { source: Track.Source.Microphone, withPlaceholder: false },
    { source: Track.Source.Unknown, withPlaceholder: false },
  ]);
  
  const audioRefs = useRef(new Map());
  const containerRef = useRef(null);

  useEffect(() => {
    console.log('🔍 检测到的轨道数量:', tracks.length);

    tracks.forEach((trackReference) => {
      const { publication, participant } = trackReference;
      
      console.log('📡 轨道信息:', {
        trackSid: publication.trackSid,
        source: Track.Source[publication.source],
        kind: publication.kind,
        participant: participant.identity,
        isLocal: participant.isLocal,
        isMuted: publication.isMuted,
        isSubscribed: publication.isSubscribed,
      });

      if (participant.isLocal) {
        console.log('⏭️ 跳过本地轨道 (自己的声音)');
        return;
      }

      if (publication.kind === Track.Kind.Audio) {
        const track = publication.track;
        
        if (track) {
          if (!audioRefs.current.has(publication.trackSid)) {
            const audioElement = document.createElement('audio');
            audioElement.autoplay = true;
            audioElement.playsInline = true;
            audioElement.volume = 1.0;

            if (containerRef.current) {
              containerRef.current.appendChild(audioElement);
            }
            
            audioRefs.current.set(publication.trackSid, audioElement);
            console.log('🎵 创建新的 audio 元素，trackSid:', publication.trackSid);
          }

          const element = audioRefs.current.get(publication.trackSid);
          track.attach(element);
          
          const playAudio = async () => {
            try {
              await element.play();
              console.log('✅ AI音频开始播放, trackSid:', publication.trackSid);
            } catch (error) {
              console.warn('⚠️ 自动播放被阻止:', error);
              console.log('💡 提示：请点击页面任意位置以允许音频播放');
            }
          };
          
          playAudio();
        } else {
          console.warn('⚠️ 轨道对象为空');
        }
      }
    });

    return () => {
      tracks.forEach((trackReference) => {
        const { publication } = trackReference;
        const track = publication?.track;
        if (track) {
          const element = audioRefs.current.get(publication.trackSid);
          if (element) {
            track.detach(element);
            element.remove();
            audioRefs.current.delete(publication.trackSid);
            console.log('🗑️ 清理音频元素:', publication.trackSid);
          }
        }
      });
    };
  }, [tracks]);

  return (
    <div>
      <div ref={containerRef} style={{ display: 'none' }} />
      
      <div style={{ 
        margin: '10px 0', 
        padding: '10px', 
        backgroundColor: '#e3f2fd', 
        borderRadius: '5px' 
      }}>
        <h3>🎵 音频轨道 ({tracks.length})</h3>
        {tracks.length === 0 ? (
          <p style={{ color: '#999', fontSize: '12px' }}>暂无音频轨道</p>
        ) : (
          tracks.map((trackRef) => (
            <div 
              key={trackRef.publication.trackSid} 
              style={{ 
                fontSize: '12px', 
                marginBottom: '5px',
                padding: '5px',
                backgroundColor: trackRef.participant.isLocal ? '#fff9c4' : '#c8e6c9',
                borderRadius: '3px'
              }}
            >
              • <strong>{trackRef.participant.identity}</strong> - 
              {Track.Source[trackRef.publication.source]} - 
              {trackRef.publication.kind}
              {trackRef.participant.isLocal && ' 🎤 (本地)'}
              {!trackRef.participant.isLocal && ' 🤖 (远程)'}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default App;