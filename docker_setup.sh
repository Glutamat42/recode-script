# start container (outdated, see below)
```bash
docker run -d --privileged -v /media/bigdata/model:/model -p 3525:22 --cpus 52 --rm --name testing debian tail -f /dev/null
# docker ps | grep debian
docker exec -it testing bash
```

# slow "screen" command potential fix
# my container needs following fix (source github issue):
# Solved by adding this lines to entrypoint start:

# ulimit -Sn 10000
# ulimit -Hn 50000

docker run -d --privileged -v /media/bigdata/model:/model -p 3525:22 --cpus 48 --rm --name testing debian bash -c "ulimit -Sn 10000 && ulimit -Hn 50000 && tail -f /dev/null"
docker exec -it testing bash




# setup inside container
```bash
apt-get update && apt-get dist-upgrade -y
apt-get install htop rsync cryptsetup screen nano python3 python3-tqdm openssh-server -y

# ssh key login
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJ2R4vCOZn8foG9vIP7buGklX3ghb59ok2FbbFmqNf0q pubkey" > ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

# configure sshd
sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin yes/' /etc/ssh/sshd_config
service ssh start

# ffmpeg system dependencies
apt-get -y install \
  autoconf \
  automake \
  build-essential \
  cmake \
  git-core \
  libass-dev \
  libfreetype6-dev \
  libgnutls28-dev \
  libmp3lame-dev \
  libsdl2-dev \
  libtool \
  libva-dev \
  libvdpau-dev \
  libvorbis-dev \
  libxcb1-dev \
  libxcb-shm0-dev \
  libxcb-xfixes0-dev \
  meson \
  ninja-build \
  pkg-config \
  texinfo \
  wget \
  yasm \
  zlib1g-dev \
  nasm \
  libopus-dev \
  libx264-dev \
  libx265-dev \
  libnuma-dev \
  libunistring-dev

# create compress user
useradd -m -s /bin/bash compress

# switch to compress user for building ffmpeg
su - compress << 'EOF'

# build ffmpeg
mkdir -p ~/ffmpeg_sources ~/bin

# svt-av1
cd ~/ffmpeg_sources 
git clone https://github.com/psy-ex/svt-av1-psy.git SVT-AV1
mkdir -p SVT-AV1/build 
cd SVT-AV1/build 
PATH="$HOME/bin:$PATH" cmake -G "Unix Makefiles" -DCMAKE_INSTALL_PREFIX="$HOME/ffmpeg_build" -DCMAKE_BUILD_TYPE=Release -DBUILD_DEC=OFF -DBUILD_SHARED_LIBS=OFF ..
PATH="$HOME/bin:$PATH" make -j 16
make install

# libfdk-aac
cd ~/ffmpeg_sources && \
git -C fdk-aac pull 2> /dev/null || git clone --depth 1 https://github.com/mstorsjo/fdk-aac && \
cd fdk-aac && \
autoreconf -fiv && \
./configure --prefix="$HOME/ffmpeg_build" --disable-shared && \
make && \
make install


cd ~/ffmpeg_sources 
wget -O ffmpeg-snapshot.tar.bz2 https://ffmpeg.org/releases/ffmpeg-snapshot.tar.bz2 
tar xjvf ffmpeg-snapshot.tar.bz2 
cd ffmpeg 
PATH="$HOME/bin:$PATH" PKG_CONFIG_PATH="$HOME/ffmpeg_build/lib/pkgconfig" ./configure \
  --prefix="$HOME/ffmpeg_build" \
  --pkg-config-flags="--static" \
  --extra-cflags="-I$HOME/ffmpeg_build/include" \
  --extra-ldflags="-L$HOME/ffmpeg_build/lib" \
  --extra-libs="-lpthread -lm" \
  --ld="g++" \
  --bindir="$HOME/bin" \
  --enable-gpl \
  --enable-gnutls \
  --enable-libass \
  --enable-libfreetype \
  --enable-libmp3lame \
  --enable-libopus \
  --enable-libfdk-aac \
  --enable-libsvtav1 \
  --enable-libvorbis \
  --enable-libx264 \
  --enable-libx265 \
  --enable-nonfree
PATH="$HOME/bin:$PATH" make -j 32
make install
hash -r
echo export PATH="$HOME/bin:$PATH" >> ~/.bashrc

EOF

# end of compress user context







cryptsetup open /model model
mount /dev/mapper/model /mnt
```

following fixes were used, but need further testing
```bash
apt-get install -y util-linux
mknod /dev/loop0 b 7 0
# cryptsetup open /model model
```